# Phase 4.5 live progress clock

SSE remains the authoritative push channel. The frontend animates elapsed and
remaining time locally from the latest backend snapshot using one shared 1s
ticker (`liveProgressClockStore`).

- Elapsed = snapshot elapsed + monotonic seconds since snapshot receipt  
- Remaining = max(0, backend estimate − local delta)  
- Overdue → “Recalculating estimate…” (never sticky “0 seconds”)  
- Unavailable → “Calculating estimate…”  
- Hidden tabs pause the display ticker only; SSE stays open  
- Timer ticks must not remount the PDF.js viewer

See ADR 0027 and ADR 0028.
