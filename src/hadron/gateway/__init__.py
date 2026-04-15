"""SSE Gateway — lightweight, always-on service for real-time event streaming.

Separated from the main controller so that the controller can scale to zero
via KEDA while the gateway maintains long-lived SSE connections for the
dashboard.  The gateway is read-only — it subscribes to Redis Streams and
queries the DB for active CRs, but never mutates state.
"""
