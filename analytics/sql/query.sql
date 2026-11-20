WITH archived_plays AS (
    SELECT p.listener, play.played_at AS played_at, play.track AS track,
           row_number() OVER (
               PARTITION BY p.listener, play.played_at,
                   coalesce(nullif(play.track.id, ''), play.track.uri, play.track.name)
               ORDER BY p.collection_date DESC, p."$path" DESC
           ) AS copy_number
    FROM "{{database}}"."spotify_raw_pages" p
    CROSS JOIN UNNEST(p.items) AS t(play)
    WHERE p.collection_date >= '{{start_date}}'
      AND p.collection_date <= '{{end_date}}'
), plays AS (
    SELECT listener, played_at, track
    FROM archived_plays
    WHERE copy_number = 1
)
{{analysis}}
