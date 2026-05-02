# Architecture Diagrams: Threading Strategy

## Original Architecture (Sequential)

```
┌─────────────────────────────────────┐
│      fetch_all_news()               │
│       (Main Thread)                 │
└────────────┬────────────────────────┘
             │
             ├─→ fetch_newsapi() ──────────┐
             │    │                         │
             │    ├─→ Route 1 [request]     │
             │    │   └─→ [wait 20s] ──────┼─→ 20s
             │    │                         │
             │    ├─→ Route 2 [request]     │
             │    │   └─→ [wait 20s]        │
             │    │                         │
             │    └─→ parse & return ◄─────┘
             │
             ├─→ fetch_rss() ───────────────────────────┐
             │    │                                      │
             │    ├─→ Feed 1 [request]                   │
             │    │   └─→ [wait 20s] ───────────────────┼─→ 60s
             │    │                                      │
             │    ├─→ Feed 2 [request]                   │
             │    │   └─→ [wait 20s]                     │
             │    │                                      │
             │    ├─→ Feed 3 [request]                   │
             │    │   └─→ [wait 20s]                     │
             │    │                                      │
             │    └─→ parse & return ◄──────────────────┘
             │
             └─→ return combined items

TOTAL TIME: ~80 seconds ⏰
```

---

## Optimized Architecture (Multithreaded)

```
┌──────────────────────────────────────────────────┐
│       fetch_all_news_threaded()                  │
│          (Main Thread + Executor)                │
└───────────────────┬──────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
    
    ThreadPool(2)          ThreadPool(2)
    ┌─────────────┐        ┌──────────────┐
    │ NewsAPI Job │        │  RSS Job     │
    │ (Thread 1)  │        │ (Thread 2)   │ ◄─── Run SIMULTANEOUSLY
    └──────┬──────┘        └──────┬───────┘
           │                      │
      ThreadPool(2)          ThreadPool(8)
      ┌─────────────┐        ┌─────────────────────────────┐
      │ Route1 Thr1 │        │ Feed1 Thr1 ┌─ Feed4 Thr5    │
      │ [wait 20s]  │        │ [wait 20s]  │ [wait 20s]    │
      │             │        │             │               │
      │ Route2 Thr2 │        │ Feed2 Thr2 ┌─ Feed5 Thr6    │
      │ [wait 20s]  │        │ [wait 20s]  │ [wait 20s]    │
      │             │        │             │               │
      │             │        │ Feed3 Thr3 ┌─ Feed6 Thr7    │
      │             │        │ [wait 20s]  │ [wait 20s]    │
      │             │        └─────────────┴───────────────┘
      └──────┬──────┘              ▲
             │◄──────────────────────┤
             │  (All waiting on I/O)  │
             ▼
        Join results
        [All done in ~20 seconds]

TOTAL TIME: ~20 seconds ⚡ (4x faster)
```

---

## Thread Lifecycle

```
Main Thread Creates ThreadPoolExecutor(max_workers=8)
│
├─ Worker Thread 1 ──→ Fetch RSS Feed 1 ──→ Parse ──→ Return
├─ Worker Thread 2 ──→ Fetch RSS Feed 2 ──→ Parse ──→ Return
├─ Worker Thread 3 ──→ Fetch RSS Feed 3 ──→ Parse ──→ Return
├─ Worker Thread 4 ──→ Fetch RSS Feed 4 ──→ Parse ──→ Return
├─ Worker Thread 5 ──→ Fetch RSS Feed 5 ──→ Parse ──→ Return
├─ Worker Thread 6 ──→ Fetch NewsAPI Route 1 ──→ Parse ──→ Return
├─ Worker Thread 7 ──→ Fetch NewsAPI Route 2 ──→ Parse ──→ Return
└─ Worker Thread 8 ──→ [Idle, waiting for reuse]

Main Thread waits for all futures to complete with as_completed()
│
└─→ All workers finish
    └─→ ThreadPoolExecutor shut down
        └─→ Results combined and returned
```

---

## Data Flow: Original vs Optimized

### Original (Sequential)

```
Main Thread: fetch_all_news()
│
├─ Call fetch_newsapi()
│  ├─ GET https://api.newsapi.org/v2/top-headlines?country=in
│  │  └─ Wait for response [████░░░░░░░░░░░░░░░░] 20s
│  ├─ GET https://api.newsapi.org/v2/top-headlines?language=en
│  │  └─ Wait for response [████░░░░░░░░░░░░░░░░] 20s
│  └─ Return 50 items
│
├─ Call fetch_rss()
│  ├─ GET https://feeds.example.com/feed1
│  │  └─ Wait for response [████░░░░░░░░░░░░░░░░] 20s
│  ├─ GET https://feeds.example.com/feed2
│  │  └─ Wait for response [████░░░░░░░░░░░░░░░░] 20s
│  ├─ GET https://feeds.example.com/feed3
│  │  └─ Wait for response [████░░░░░░░░░░░░░░░░] 20s
│  └─ Return 75 items
│
└─ Combine and return 125 items
   Total time: ~80 seconds
```

### Optimized (Concurrent)

```
Main Thread: fetch_all_news_threaded()
│
├─ Create ThreadPool(2) for NewsAPI + RSS
│
├─ Submit fetch_newsapi_threaded() to Thread 1
│  └─ CREATE ThreadPool(2) inside
│     ├─ GET https://api.newsapi.org/v2/top-headlines?country=in
│     │  └─ Wait for response [████░░░░░░░░░░░░░░░░] 20s
│     └─ GET https://api.newsapi.org/v2/top-headlines?language=en
│        └─ Wait for response [████░░░░░░░░░░░░░░░░] 20s (CONCURRENT)
│
├─ Submit fetch_rss_threaded() to Thread 2 (RUNNING SIMULTANEOUSLY)
│  └─ CREATE ThreadPool(8) inside
│     ├─ GET https://feeds.example.com/feed1
│     │  └─ Wait [████░░░░░░░░░░░░░░░░] 20s
│     ├─ GET https://feeds.example.com/feed2
│     │  └─ Wait [████░░░░░░░░░░░░░░░░] 20s (CONCURRENT)
│     ├─ GET https://feeds.example.com/feed3
│     │  └─ Wait [████░░░░░░░░░░░░░░░░] 20s (CONCURRENT)
│     └─ Return 75 items
│
└─ Wait for both branches with as_completed()
   ├─ NewsAPI branch done: 50 items
   └─ RSS branch done: 75 items
   └─ Combine and return 125 items
      Total time: ~20 seconds
```

---

## Thread Pool Sizing Strategy

```
LEVEL 1: Main Fetch Coordinator
┌────────────────────────┐
│  ThreadPool(max=2)     │
│  ├─ NewsAPI Thread     │
│  └─ RSS Thread         │
└──────────┬─────────────┘
           │
    ┌──────┴──────┐
    ▼             ▼

LEVEL 2a: NewsAPI Routes        LEVEL 2b: RSS Feeds
┌──────────────────┐             ┌──────────────────────────┐
│ ThreadPool(max=2)│             │ ThreadPool(max=8)        │
│ ├─ Route1 Thr    │             │ ├─ Feed1 Thr             │
│ └─ Route2 Thr    │             │ ├─ Feed2 Thr             │
│                  │             │ ├─ ...                   │
│ (Only 2 routes)  │             │ ├─ FeedN Thr             │
└──────────────────┘             │ └─ ...up to 8 max        │
                                 └──────────────────────────┘
                                 (Typically 3-10 RSS feeds)
```

---

## Error Handling Flow

```
Main Thread
│
├─ ThreadPool(2): [NewsAPI | RSS]
│  │
│  ├─ NewsAPI Branch (Thread 1)
│  │  └─ ThreadPool(2): [Route1 | Route2]
│  │     ├─ Route 1 ──→ [OK] ✓ Add 25 items
│  │     └─ Route 2 ──→ [TIMEOUT] ✗ Log error, add 0 items
│  │     └─ Return items + log failures
│  │
│  └─ RSS Branch (Thread 2)
│     └─ ThreadPool(8): [Feed1...Feed8]
│        ├─ Feed 1 ──→ [OK] ✓ Add 20 items
│        ├─ Feed 2 ──→ [TIMEOUT] ✗ Log error, skip
│        ├─ Feed 3 ──→ [OK] ✓ Add 18 items
│        ├─ Feed 4 ──→ [404] ✗ Log error, skip
│        └─ ... continue with others
│        └─ Return partial items + log failures
│
└─ Main combines:
   source_breakdown = {'newsapi': 25, 'rss': 67}
   (One feed failed → just skip it, return what we got)
```

---

## Memory Architecture

### Original (1 Connection)
```
Python Process
├─ Main Thread (Main Stack)
│  └─ fetch_all_news() stack frame
│     ├─ Response 1 buffer: ~50KB
│     └─ Response 2 buffer: ~50KB
└─ ~100KB network buffers
   Total heap: ~5-10MB
```

### Optimized (8 Connections)
```
Python Process
├─ Main Thread (Main Stack)
│  └─ fetch_all_news_threaded() stack frame
├─ Worker Thread 1 stack + 50KB response buffer
├─ Worker Thread 2 stack + 50KB response buffer
├─ Worker Thread 3 stack + 50KB response buffer
├─ Worker Thread 4 stack + 50KB response buffer
├─ Worker Thread 5 stack + 50KB response buffer
├─ Worker Thread 6 stack + 50KB response buffer
├─ Worker Thread 7 stack + 50KB response buffer
├─ Worker Thread 8 stack + 50KB response buffer
└─ ~800KB network buffers (8 concurrent)
   Total heap: ~15-25MB
   Overhead: ~10-15MB more
```

**Result:** Negligible memory increase for 4-5x speedup

---

## CPU Usage Over Time

### Original
```
CPU Utilization:
100% ├─────────────────────────────────────────────────────────
     │ [Network I/O wait, barely any CPU]
 50% │
  0% └─────────────────────────────────────────────────────────
     0s                                                    80s

Single thread: Blocked waiting for network (I/O bound)
```

### Optimized
```
CPU Utilization:
100% ├──────────┐ ┌──────────┐
     │          │ │          │ [Thread switching overhead]
 50% │          └─┘          └──────────┐
  0% └──────────────────────────────────────────────────────
     0s                                    20s

Multiple threads: Minor CPU overhead from context switching
(GIL released during network I/O)
```

**Result:** Same effective CPU time, but 4x wall-clock speedup

---

## Summary: Why This Architecture Works

1. **I/O Bound, Not CPU Bound**
   - Network requests release the GIL
   - Threads can run while others wait
   - 4-5x speedup from perfect concurrency

2. **Independent Operations**
   - Each feed fetch is independent
   - No shared state → no locks needed
   - Each thread has its own request session

3. **Thread Pool Reuse**
   - Threads created once, reused many times
   - No per-request overhead
   - Minimal context switching

4. **Error Isolation**
   - One feed timing out doesn't affect others
   - Exceptions caught per-thread
   - System continues gracefully

5. **Backward Compatibility**
   - Same function signatures
   - Same data structures
   - Drop-in replacement
