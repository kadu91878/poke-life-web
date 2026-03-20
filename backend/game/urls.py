from django.urls import path

from . import views

urlpatterns = [
    # ── Catálogo de cartas ──────────────────────────────────────────────────
    path('health/', views.HealthcheckView.as_view(), name='healthcheck'),
    path('cards/', views.CardCatalogView.as_view(), name='card-catalog'),
    path('cards/<str:card_id>/', views.CardDetailView.as_view(), name='card-detail'),

    # ── Salas ───────────────────────────────────────────────────────────────
    path('rooms/', views.RoomListView.as_view(), name='room-list'),
    path('rooms/create/', views.CreateRoomView.as_view(), name='room-create'),
    path('rooms/<str:room_code>/', views.RoomDetailView.as_view(), name='room-detail'),
    path('rooms/<str:room_code>/join/', views.JoinRoomView.as_view(), name='room-join'),
    path('rooms/<str:room_code>/start/', views.StartGameView.as_view(), name='room-start'),
    path('rooms/<str:room_code>/add-cpu/', views.AddCpuPlayerView.as_view(), name='room-add-cpu'),
    path('rooms/<str:room_code>/select-starter/', views.SelectStarterView.as_view(), name='room-select-starter'),
    path('rooms/<str:room_code>/roll/', views.RollDiceView.as_view(), name='room-roll'),
    path('rooms/<str:room_code>/move/', views.MovePlayerView.as_view(), name='room-move'),
    path('rooms/<str:room_code>/resolve-tile/', views.ResolveTileView.as_view(), name='room-resolve-tile'),
    path('rooms/<str:room_code>/pass-turn/', views.PassTurnView.as_view(), name='room-pass-turn'),
    path('rooms/<str:room_code>/leave/', views.LeaveRoomView.as_view(), name='room-leave'),
    path('rooms/<str:room_code>/remove-player/', views.RemovePlayerView.as_view(), name='room-remove-player'),
    path('rooms/<str:room_code>/save-state/', views.SaveStateView.as_view(), name='room-save-state'),
    path('rooms/<str:room_code>/restore-state/', views.RestoreStateView.as_view(), name='room-restore-state'),
]
