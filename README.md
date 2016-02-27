fake_ntp_server
===============

This is a simple fake NTP server.

The server currently tries to convince the client that the client clock is 400 PPM too fast.
This leads to the client slowing its clock, which leads it to slowly move out of sync.
