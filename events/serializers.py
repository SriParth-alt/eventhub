from django.db import transaction
from rest_framework import serializers

from .models import Event, Reservation


class EventSerializer(serializers.ModelSerializer):
    reservations_count = serializers.SerializerMethodField()

    class Meta:
        model  = Event
        fields = ['id', 'title', 'venue', 'date', 'total_seats',
                  'available_seats', 'status', 'created_at', 'reservations_count']

    def get_reservations_count(self, obj):
        return obj.reservations.filter(status='confirmed').count()

    def validate(self, data):
        # On partial updates (PATCH) fall back to the stored values
        total     = data.get('total_seats', getattr(self.instance, 'total_seats', 0))
        available = data.get('available_seats', getattr(self.instance, 'available_seats', 0))
        if available > total:
            raise serializers.ValidationError('available_seats cannot exceed total_seats.')
        return data


class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model            = Reservation
        fields           = ['id', 'event', 'attendee_name', 'attendee_email',
                            'seats_reserved', 'status', 'created_at']
        read_only_fields = ['status', 'created_at']

    def validate_seats_reserved(self, value):
        if value < 1:
            raise serializers.ValidationError('Must reserve at least 1 seat.')
        return value

    def validate(self, data):
        event = data.get('event')
        if event.status not in ('upcoming', 'ongoing'):
            raise serializers.ValidationError(
                f'Cannot reserve seats for a {event.status} event.'
            )
        if data.get('seats_reserved', 0) > event.available_seats:
            raise serializers.ValidationError(
                f'Only {event.available_seats} seat(s) available.'
            )
        return data

    def create(self, validated_data):
        # Lock the event row so two simultaneous requests can't both take the last seat.
        # The seat deduction and the reservation insert commit together or not at all.
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=validated_data['event'].pk)
            seats = validated_data['seats_reserved']
            if seats > event.available_seats:
                raise serializers.ValidationError(
                    {'non_field_errors': [f'Only {event.available_seats} seat(s) available.']}
                )
            event.available_seats -= seats
            event.save()
            validated_data['event'] = event
            return Reservation.objects.create(**validated_data)
