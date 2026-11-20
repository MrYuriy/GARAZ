#!/usr/bin/env bash
# Empty the registers before going live: incidents (with photos), permits (with
# scans), operators and trucks. Kept: users, dictionaries, the truck catalogue
# (makes and models), the permit logo. The audit log is kept unless --audit.
#
# Run on the server, from the GARAZ directory:
#   bash scripts/purge_register.sh           # dry run: only counts
#   bash scripts/purge_register.sh --yes     # dump the database first, then purge
#   bash scripts/purge_register.sh --yes --audit   # also empty the audit log
#
# Cannot be undone except from the dump it writes first (or the hourly backups).
set -euo pipefail

DB=garaz-db
API=garaz-api
PSQL=(docker exec "$DB" psql -U garaz -d garaz -v ON_ERROR_STOP=1)

yes=false
audit=false
for arg in "$@"; do
  case "$arg" in
    --yes) yes=true ;;
    --audit) audit=true ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

echo "What is there now:"
"${PSQL[@]}" -tAc "
  select 'zgłoszenia (incidents)', count(*) from incidents union all
  select 'zdjęcia zgłoszeń', count(*) from incident_photos union all
  select 'uprawnienia (permits)', count(*) from permits union all
  select 'operatorzy', count(*) from operators union all
  select 'wózki', count(*) from trucks union all
  select 'dziennik (audit_logs)', count(*) from audit_logs" | sed 's/|/: /'
echo "Files: $(docker exec "$API" sh -c 'du -sh $STORAGE_DIR/incidents $STORAGE_DIR/permits 2>/dev/null | tr "\n" " "')"

if ! $yes; then
  echo
  echo "Dry run — nothing changed. Add --yes to purge (and --audit to empty the audit log too)."
  exit 0
fi

dump_dir="${DUMP_DIR:-$HOME/Desktop/backups/garaz}"
mkdir -p "$dump_dir"
dump="$dump_dir/before_purge_$(date +%Y-%m-%d_%H-%M-%S).sql.gz"
docker exec "$DB" pg_dump -U garaz -d garaz | gzip > "$dump"
echo "Database dumped to $dump"

audit_sql=""
if $audit; then audit_sql="truncate audit_logs restart identity;"; fi

docker exec -i "$DB" psql -U garaz -d garaz -v ON_ERROR_STOP=1 <<SQL
begin;
truncate incident_events, incident_photos, incidents,
         permit_truck_types, permits, operators, trucks
         restart identity;
$audit_sql
commit;
SQL

# Photos and scans; the storage keys pointing at them are gone with the rows.
docker exec "$API" sh -c 'rm -rf "$STORAGE_DIR/incidents" "$STORAGE_DIR/permits"'
echo "Purged. Users, dictionaries, the truck catalogue and the logo are kept."
