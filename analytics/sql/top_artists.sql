SELECT artist_name, count(*) AS credited_plays
FROM plays
CROSS JOIN UNNEST(array_distinct(transform(track.artists, a -> a.name))) AS a(artist_name)
GROUP BY artist_name
ORDER BY credited_plays DESC, artist_name
LIMIT 10
