# EventHub

A backend API for a simplified event ticketing platform, built with Django and Django REST Framework. Users can browse events, reserve seats, and cancel reservations.

## How to run

```bash
git clone <this-repo-url>
cd eventhub

python -m venv venv
# Windows: venv\Scripts\activate     macOS/Linux: source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API is served at `http://127.0.0.1:8000/api/`. The DRF browsable API works in the browser too.

Run the test suite (covers every item in the testing checklist):

```bash
python manage.py test events
```

## Endpoints

### Events

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/events/` | List all events, ordered by date |
| POST   | `/api/events/` | Create an event. `available_seats` cannot exceed `total_seats` |
| GET    | `/api/events/{id}/` | Get a single event, including `reservations_count` (confirmed reservations) |
| PUT    | `/api/events/{id}/` | Update an event |
| DELETE | `/api/events/{id}/` | Delete an event (its reservations are deleted with it) |
| GET    | `/api/events/?status=upcoming` | Filter by status (`upcoming`, `ongoing`, `completed`, `cancelled`) |
| GET    | `/api/events/?venue=mumbai` | Filter by venue (case-insensitive, partial match) |

### Reservations

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/reservations/` | List all reservations, newest first |
| POST   | `/api/reservations/` | Create a reservation. Deducts the seats from the event. Returns 400 if the event is not `upcoming`/`ongoing`, if `seats_reserved < 1`, or if there aren't enough seats |
| GET    | `/api/reservations/{id}/` | Get a single reservation |
| GET    | `/api/reservations/?event_id=1` | Filter reservations by event |
| POST   | `/api/reservations/{id}/cancel/` | Cancel a reservation and give its seats back to the event. Returns 400 if it's already cancelled |

### Sample requests

Create an event: `POST /api/events/`

```json
{
  "title": "PyCon India 2025",
  "venue": "NIMHANS Convention Centre, Bangalore",
  "date": "2025-09-20",
  "total_seats": 500,
  "available_seats": 500,
  "status": "upcoming"
}
```

Reserve seats: `POST /api/reservations/` returns `201 Created`

```json
{
  "event": 1,
  "attendee_name": "Priya Sharma",
  "attendee_email": "priya@example.com",
  "seats_reserved": 2
}
```

Overbooking returns `400 Bad Request`:

```json
{ "non_field_errors": ["Only 1 seat(s) available."] }
```

Cancel: `POST /api/reservations/1/cancel/` (no body) returns the reservation with `"status": "cancelled"`.

### Request logging

`events/middleware.py` contains `RequestLoggingMiddleware`, which logs every request to the terminal:

```
POST /api/reservations/ - 201 - 0.02s
```

## Project structure

```
eventhub/
├── manage.py
├── eventhub/          # settings.py, urls.py
├── events/
│   ├── models.py        # Event, Reservation
│   ├── serializers.py   # validation + seat deduction
│   ├── views.py         # ModelViewSets, cancel action
│   ├── urls.py          # DefaultRouter
│   ├── middleware.py    # RequestLoggingMiddleware
│   ├── tests.py
│   └── migrations/
└── requirements.txt
```

## Design decisions

### 1. Reservations can be created and cancelled, but not edited or deleted

`ReservationViewSet` is a `ModelViewSet`, which gives you PUT, PATCH and DELETE by default. I restricted it with `http_method_names = ['get', 'post', 'head', 'options']`.

**Why:** an event's `available_seats` only stays correct if every seat change goes through code that updates it. A `PATCH` changing `seats_reserved` from 2 to 10, or a `DELETE` on a confirmed reservation, would change the seats a reservation holds without changing the event's count, and the numbers would drift. Cancelling through `/cancel/` instead keeps a record of the reservation and returns the seats properly. This also matches the endpoint table in the brief, which lists no PUT or DELETE for reservations.

### 2. Seat changes run inside `transaction.atomic()` with a row lock

The brief says that putting the seat deduction and the reservation insert in one `create()` is enough for this assignment, and leaves `transaction.atomic()` for a later session. I added it anyway, because the race condition it prevents is the main problem a ticketing system has to solve:

- `create()` and `cancel` re-read the event with `select_for_update()` inside `transaction.atomic()`. If two requests try to book the last seat at the same moment, the second waits until the first is done, then sees the updated count and gets a 400.
- If anything fails partway through, the seat deduction and the reservation insert are both rolled back, so seats are never taken without a reservation existing.

SQLite locks the whole database on write, so locally this mostly guarantees all-or-nothing writes. On PostgreSQL or MySQL, `select_for_update()` is what actually serializes concurrent bookings.

### 3. `EventSerializer.validate` handles partial updates

The validator compares the incoming `available_seats`/`total_seats` against the event's stored values when a field is missing. Without that, a `PATCH {"available_seats": 50}` would be compared to a `total_seats` of 0 and wrongly rejected.
