from rest_framework.test import APITestCase

from .models import Event, Reservation


class EventHubTests(APITestCase):
    def setUp(self):
        self.event = Event.objects.create(
            title='PyCon India 2025', venue='NIMHANS Convention Centre, Bangalore',
            date='2025-09-20', total_seats=3, available_seats=3, status='upcoming',
        )
        Event.objects.create(
            title='DevFest', venue='Jio World Centre, Mumbai',
            date='2025-10-01', total_seats=100, available_seats=100, status='completed',
        )

    def reserve(self, seats, event=None):
        return self.client.post('/api/reservations/', {
            'event': (event or self.event).id,
            'attendee_name': 'Priya Sharma',
            'attendee_email': 'priya@example.com',
            'seats_reserved': seats,
        }, format='json')

    def test_create_event(self):
        res = self.client.post('/api/events/', {
            'title': 'New Event', 'venue': 'Delhi', 'date': '2025-12-01',
            'total_seats': 10, 'available_seats': 10,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['reservations_count'], 0)

    def test_available_cannot_exceed_total(self):
        res = self.client.post('/api/events/', {
            'title': 'Bad', 'venue': 'Delhi', 'date': '2025-12-01',
            'total_seats': 10, 'available_seats': 11,
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_list_and_filter_events(self):
        self.assertEqual(len(self.client.get('/api/events/').data), 2)
        self.assertEqual(len(self.client.get('/api/events/?status=upcoming').data), 1)
        self.assertEqual(self.client.get('/api/events/?venue=mumbai').data[0]['title'], 'DevFest')

    def test_reservation_deducts_seats(self):
        res = self.reserve(2)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'confirmed')
        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 1)

    def test_overbooking_returns_400(self):
        self.reserve(2)
        res = self.reserve(2)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['non_field_errors'], ['Only 1 seat(s) available.'])

    def test_zero_seats_rejected(self):
        self.assertEqual(self.reserve(0).status_code, 400)

    def test_cannot_reserve_completed_event(self):
        completed = Event.objects.get(status='completed')
        self.assertEqual(self.reserve(1, completed).status_code, 400)

    def test_cancel_restores_seats(self):
        rid = self.reserve(2).data['id']
        res = self.client.post(f'/api/reservations/{rid}/cancel/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'cancelled')
        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 3)
        # Cancelling twice is rejected and doesn't add seats again
        self.assertEqual(self.client.post(f'/api/reservations/{rid}/cancel/').status_code, 400)
        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 3)

    def test_filter_reservations_by_event(self):
        self.reserve(1)
        other = Event.objects.create(title='X', venue='Y', date='2025-11-01',
                                     total_seats=5, available_seats=5)
        self.reserve(1, other)
        res = self.client.get(f'/api/reservations/?event_id={self.event.id}')
        self.assertEqual(len(res.data), 1)

    def test_reservation_edit_and_delete_not_allowed(self):
        rid = self.reserve(1).data['id']
        self.assertEqual(self.client.delete(f'/api/reservations/{rid}/').status_code, 405)
        self.assertEqual(self.client.patch(f'/api/reservations/{rid}/', {'seats_reserved': 3}).status_code, 405)
        self.assertTrue(Reservation.objects.filter(id=rid).exists())
