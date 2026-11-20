SELECT listener, count(*) AS plays,
       round(sum(coalesce(track.duration_ms, 0)) / 60000.0, 2) AS estimated_minutes
FROM plays
GROUP BY listener
ORDER BY listener
