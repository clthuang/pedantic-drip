# Rate Limiting for API Endpoints

## Topic Description

Add rate limiting to API endpoints to protect public endpoints from abuse with configurable per-client rate limits. The implementation should support both sliding window and token bucket algorithms, with seamless integration into existing auth middleware. Rate limiting decisions should be fast (sub-millisecond latency), distributed across service instances, and configurable per endpoint and per client tier. Rejected requests should provide clear Retry-After headers to clients. The solution must handle edge cases like clock skew in distributed systems, graceful degradation when the rate limit backend is unavailable, and accurate quota reporting for client visibility.
