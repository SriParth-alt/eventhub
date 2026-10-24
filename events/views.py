from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Event, Reservation
from .serializers import EventSerializer, ReservationSerializer


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer

    def get_queryset(self):
        queryset     = Event.objects.all()
        status_param = self.request.query_params.get('status')
        venue_param  = self.request.query_params.get('venue')
        if status_param:
            queryset = queryset.filter(status=status_param)
        if venue_param:
            queryset = queryset.filter(venue__icontains=venue_param)
        return queryset


class ReservationViewSet(viewsets.ModelViewSet):
    serializer_class = ReservationSerializer
    # Reservations are created and cancelled, never edited or deleted:
    # PUT/PATCH/DELETE would change seats_reserved without touching the event's seat count.
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = Reservation.objects.all()
        event_id = self.request.query_params.get('event_id')
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    # detail=True means URL is /reservations/{id}/cancel/
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        if reservation.status == 'cancelled':
            return Response({'error': 'Already cancelled.'}, status=400)

        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=reservation.event_id)
            event.available_seats += reservation.seats_reserved
            event.save()
            reservation.status = 'cancelled'
            reservation.save()

        return Response(self.get_serializer(reservation).data)
