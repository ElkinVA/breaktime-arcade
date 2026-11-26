from __future__ import annotations

from django.urls import path

from apps.rooms.api.views import (
    RoomCommandView,
    RoomCreateView,
    RoomDetailView,
    RoomJoinView,
    RoomLeaveView,
)

app_name = "rooms"

urlpatterns = [
    path("rooms", RoomCreateView.as_view(), name="room-create"),
    path("rooms/join", RoomJoinView.as_view(), name="room-join"),
    path("rooms/<uuid:room_id>", RoomDetailView.as_view(), name="room-detail"),
    path("rooms/<uuid:room_id>/commands", RoomCommandView.as_view(), name="room-command"),
    path("rooms/<uuid:room_id>/leave", RoomLeaveView.as_view(), name="room-leave"),
]
