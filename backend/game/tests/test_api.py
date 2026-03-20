from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class RoomApiTests(APITestCase):
    def test_healthcheck(self):
        response = self.client.get(reverse('healthcheck'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'status': 'ok'})

    def _create_room(self):
        response = self.client.post(reverse('room-create'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response.data['room_code']

    def _join(self, room_code: str, player_name: str):
        response = self.client.post(reverse('room-join', kwargs={'room_code': room_code}), {'player_name': player_name}, format='json')
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        return response.data['player_id']

    def test_create_join_and_start_game(self):
        room_code = self._create_room()
        host_id = self._join(room_code, 'Ash')
        self._join(room_code, 'Misty')

        start = self.client.post(reverse('room-start', kwargs={'room_code': room_code}), {'player_id': host_id}, format='json')
        self.assertEqual(start.status_code, status.HTTP_200_OK)
        state = start.data['state']
        self.assertEqual(state['status'], 'playing')
        self.assertEqual(state['turn']['phase'], 'select_starter')

    def test_turn_flow_move_blocks_pass_turn_when_interaction_is_pending(self):
        room_code = self._create_room()
        host_id = self._join(room_code, 'Ash')
        player2_id = self._join(room_code, 'Misty')

        self.client.post(reverse('room-start', kwargs={'room_code': room_code}), {'player_id': host_id}, format='json')

        detail = self.client.get(reverse('room-detail', kwargs={'room_code': room_code})).data
        game_state = detail['game_state']
        starters = game_state['turn']['available_starters']
        turn_order = game_state['turn_order']

        self.client.post(reverse('room-select-starter', kwargs={'room_code': room_code}), {'player_id': turn_order[0], 'starter_id': starters[0]['id']}, format='json')
        self.client.post(reverse('room-select-starter', kwargs={'room_code': room_code}), {'player_id': turn_order[1], 'starter_id': starters[1]['id']}, format='json')

        first_player_id = turn_order[0]

        move = self.client.post(reverse('room-move', kwargs={'room_code': room_code}), {'player_id': first_player_id, 'dice_result': 2}, format='json')
        self.assertEqual(move.status_code, status.HTTP_200_OK)

        final_state = self.client.get(reverse('room-detail', kwargs={'room_code': room_code})).data['game_state']
        current = final_state['turn']['current_player_id']
        self.assertIn(current, [host_id, player2_id])
        self.assertEqual(current, first_player_id)
        self.assertEqual(final_state['turn']['phase'], 'action')
        self.assertIsNotNone(final_state['turn']['pending_action'])

        pass_turn = self.client.post(reverse('room-pass-turn', kwargs={'room_code': room_code}), {'player_id': first_player_id}, format='json')
        self.assertEqual(pass_turn.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('interação pendente', pass_turn.data['error'])

        final_state = self.client.get(reverse('room-detail', kwargs={'room_code': room_code})).data['game_state']
        self.assertEqual(final_state['turn']['current_player_id'], first_player_id)

    def test_save_restore_and_remove(self):
        room_code = self._create_room()
        host_id = self._join(room_code, 'Ash')
        player2_id = self._join(room_code, 'Brock')

        detail = self.client.get(reverse('room-detail', kwargs={'room_code': room_code}))
        state = detail.data['game_state']
        state['custom_rules'] = {'fast_mode': True}

        save_resp = self.client.post(reverse('room-save-state', kwargs={'room_code': room_code}), {'state': state}, format='json')
        self.assertEqual(save_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(save_resp.data['state']['custom_rules']['fast_mode'])

        restored_state = save_resp.data['state']
        restored_state['status'] = 'playing'
        restore_resp = self.client.post(reverse('room-restore-state', kwargs={'room_code': room_code}), {'state': restored_state}, format='json')
        self.assertEqual(restore_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(restore_resp.data['state']['status'], 'playing')

        remove = self.client.post(
            reverse('room-remove-player', kwargs={'room_code': room_code}),
            {'actor_id': host_id, 'player_id': player2_id},
            format='json',
        )
        self.assertEqual(remove.status_code, status.HTTP_200_OK)
        p2 = next(p for p in remove.data['state']['players'] if p['id'] == player2_id)
        self.assertFalse(p2['is_active'])
