# Test Plan

Automated (no database needed): `python -m unittest discover -s tests -v` — 15 tests covering
page rendering, table whitelist, read-only workflow tables, seat/payment/gate/baggage/cancel
validation and the refund tiers.

Manual (needs MySQL with sample data). Mark each Pass/Fail during your demo.

| # | Area | Steps | Expected result |
|---|------|-------|-----------------|
| 1 | Search | Booking page: pick source + destination + date | Only matching flights listed |
| 2 | Search | Search with a date that has no flights | "0 flight(s) found", no error |
| 3 | Booking | Select flight, passenger, click a green seat, Create Booking | Reservation Pending; flight's available seats drops by 1 |
| 4 | Seat conflict | Book the same seat again on that flight | Error: seat already reserved |
| 5 | One seat/passenger | Book same passenger on same flight again | Error: already has an active reservation |
| 6 | Invalid seat | Type 31A or 12G | Error: invalid seat number |
| 7 | Full flight | Book a flight with 0 available seats | Select button disabled / error |
| 8 | Payment | Pay a Pending reservation (valid method + reference) | Reservation becomes Confirmed |
| 9 | Duplicate pay | Pay the same reservation again | Error: already paid |
| 10 | Bad payment | Amount 0 or negative | Error, nothing saved |
| 11 | Ticket | Issue ticket before payment | Error: complete payment first |
| 12 | Ticket | Issue ticket after payment | Ticket TKTnnn created; repeat returns existing |
| 13 | Check-in | Check in without ticket | Error: issue ticket first |
| 14 | Check-in | Check in with gate B12 | Boarding pass BPnnn created |
| 15 | Baggage | Add weight -3 | Error; add 20 kg after check-in -> recorded |
| 16 | Seat change | Operations: click another free seat | Seat updated; old seat becomes free |
| 17 | Seat change | Change seat after check-in | Error: not allowed after check-in |
| 18 | Cancel | Cancel unpaid Pending reservation | Refund 0; seat released (+1) |
| 19 | Cancel | Cancel paid reservation 72h+ before departure | Refund 90% of paid amount |
| 20 | Cancel | Cancel a checked-in reservation | Error: cannot cancel |
| 21 | Reports | Open Reports | Manifest, occupancy, route demand, baggage, cancellations, on-time, revenue all load |
| 22 | CRUD | Passengers module: add, edit, delete a record | Success messages; list refreshes |
| 23 | CRUD | Edit a passenger and clear an optional field | Field cleared; required fields unchanged |
| 24 | Protection | Reservations module | Add/Edit/Delete hidden (read-only) |
| 25 | Errors | Stop MySQL, reload dashboard | Error toast, no crash |
