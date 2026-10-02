#!/bin/sh
set -eu

cd /app
alembic upgrade head
exec supervisord -c /app/supervisord.conf