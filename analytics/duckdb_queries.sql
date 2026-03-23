SELECT COUNT(*) FROM read_parquet('data/client=<slug>/dataset=ritten_detail/current/*.parquet');

SELECT controlecode, COUNT(*)
FROM read_parquet('data/client=<slug>/dataset=ritten_detail/current/*.parquet')
GROUP BY controlecode
ORDER BY COUNT(*) DESC;
