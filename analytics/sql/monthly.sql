SELECT listener,
       date_format(at_timezone(from_iso8601_timestamp(played_at), 'Europe/Madrid'), '%Y-%m') AS month,
       count(*) AS plays,
       round(sum(coalesce(track.duration_ms, 0)) / 60000.0, 2) AS estimated_minutes
FROM plays
GROUP BY 1, 2
ORDER BY month, listener
