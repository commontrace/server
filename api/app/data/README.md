# Bundled data

## dbip-country-lite.mmdb

IP-to-country lookup database used by `app.services.geoip` to derive an
anonymized 2-letter country code from a request's client IP (the IP itself
is never stored or logged — only the resolved country is persisted on the
user row).

- **Source:** [DB-IP IP-to-Country Lite](https://db-ip.com/db/download/ip-to-country-lite)
- **License:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- **Attribution:** IP Geolocation by DB-IP (https://db-ip.com)
- **Format:** MaxMind DB (`.mmdb`), read via the `maxminddb` package.

### Refreshing

DB-IP publishes a new free build monthly. To update:

```bash
curl -s -o /tmp/dbip.mmdb.gz \
  "https://download.db-ip.com/free/dbip-country-lite-YYYY-MM.mmdb.gz"
gunzip -f /tmp/dbip.mmdb.gz
mv /tmp/dbip.mmdb app/data/dbip-country-lite.mmdb
```

The country schema is stable (`record["country"]["iso_code"]`), so no code
change is needed on refresh.
