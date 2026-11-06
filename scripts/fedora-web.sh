#!/usr/bin/env bash
# Fedora half of the web layer: staff portal :8085, status page :8080, notes uploader :8070.
# The control room stays separate (make control-up). Run from anywhere:
#
#   scripts/fedora-web.sh setup    once, with internet: packages, MySQL, firewall, Tomcat, builds
#   scripts/fedora-web.sh start    start all three parts
#   scripts/fedora-web.sh check    PASS/FAIL for each part and each link to the Mac
#   scripts/fedora-web.sh stop     stop all three parts
#
# Needs PLATFORM_HOST, CONTROL_HOST, CS_TOKEN and MYSQL_PASSWORD in .env. Secrets stay in .env and in
# ~/tomcat/bin/setenv.sh (mode 600).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TOMCAT_VERSION=10.1.61
TOMCAT="$HOME/tomcat"
RUN="$HOME/.cascadeshield-web"
mkdir -p "$RUN"

pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; FAILS=$((FAILS + 1)); }
die() { echo "ERROR: $1" >&2; exit 1; }
FAILS=0

[ -f .env ] || die ".env missing: cp .env.example .env, then set the values listed at the top of this script"
set -a; . ./.env; set +a
: "${PLATFORM_HOST:=localhost}" "${CONTROL_HOST:=localhost}" "${CS_TOKEN:=dev-token}" "${MYSQL_PASSWORD:=}"
[ "$PLATFORM_HOST" != localhost ] || die "PLATFORM_HOST in .env must be the Mac's IP"
[ "$CONTROL_HOST" != localhost ] || die "CONTROL_HOST in .env must be this machine's IP"
# Derived here, not read from .env: .env.example's values for these are the Mac's localhost ones.
export GATEWAY_URL="http://$PLATFORM_HOST:8000" RAG_URL="http://$PLATFORM_HOST:8003"
export CORE_URL=http://localhost:8600 MYSQL_HOST=localhost MYSQL_DB=cascadeshield_web MYSQL_USER=csweb
export STATUS_PAGE_URL="http://$CONTROL_HOST:8080/status/" NOTES_URL="http://$CONTROL_HOST:8070/"
export DASHBOARD_URL="http://$CONTROL_HOST:8501/"

need_password() {
  # Only letters and digits, because it is substituted into SQL and a shell file.
  [[ "$MYSQL_PASSWORD" =~ ^[A-Za-z0-9]{8,}$ ]] && [ "$MYSQL_PASSWORD" != change-me ] \
    || die "set MYSQL_PASSWORD in .env: at least 8 letters and digits, e.g. $(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')"
}

set_java() { export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"; }

setup() {
  need_password
  echo "== packages"
  # Package names differ by Fedora release: 45 has no Java 21 and no community-mysql. Any JDK from 21 up works.
  jdk="$(dnf -q repoquery --qf '%{name}\n' java-21-openjdk-devel java-25-openjdk-devel java-latest-openjdk-devel 2>/dev/null | sort -u | head -1)"
  [ -n "$jdk" ] || die "no OpenJDK package found"
  sudo dnf install -y "$jdk" mysql-server php-cli php-mysqlnd curl tar gzip || die "dnf failed"
  set_java
  echo "== MySQL"
  sudo systemctl enable --now mysqld || die "mysqld did not start: sudo journalctl -u mysqld"
  sed "s/'change-me'/'$MYSQL_PASSWORD'/" web/sql/schema.sql | sudo mysql || die "schema.sql failed"
  sudo mysql -e "ALTER USER 'csweb'@'localhost' IDENTIFIED BY '$MYSQL_PASSWORD'" || die "could not set the password"
  echo "== firewall"
  if systemctl is-active --quiet firewalld; then
    for p in 8085 8080 8070; do sudo firewall-cmd -q --permanent --add-port=$p/tcp; done
    sudo firewall-cmd -q --reload
  fi
  echo "== Tomcat $TOMCAT_VERSION"
  if [ ! -x "$TOMCAT/bin/startup.sh" ]; then
    mkdir -p "$TOMCAT"
    curl -fsSL "https://archive.apache.org/dist/tomcat/tomcat-10/v$TOMCAT_VERSION/bin/apache-tomcat-$TOMCAT_VERSION.tar.gz" \
      | tar -xz --strip-components=1 -C "$TOMCAT" || die "Tomcat download failed"
  fi
  echo "== builds (the first takes a few minutes)"
  (cd web/staff-portal && ./mvnw -q -DskipTests package) || die "staff portal build failed"
  (cd web/status-page && ./mvnw -q -DskipTests package) || die "status page build failed"
  echo "Done. Next: scripts/fedora-web.sh start"
}

start() {
  need_password
  set_java
  jar="$(ls web/staff-portal/target/*.jar 2>/dev/null | grep -v original | head -1)"
  [ -n "$jar" ] && [ -f web/status-page/target/status.war ] && [ -x "$TOMCAT/bin/startup.sh" ] || die "not built: run setup first"

  if [ ! -f "$RUN/staff.pid" ] || ! kill -0 "$(cat "$RUN/staff.pid")" 2>/dev/null; then
    nohup "$JAVA_HOME/bin/java" -jar "$jar" --spring.profiles.active=prod >"$RUN/staff.log" 2>&1 </dev/null &
    echo $! >"$RUN/staff.pid"
  fi

  (umask 077; cat >"$TOMCAT/bin/setenv.sh" <<ENV
export JAVA_HOME=$JAVA_HOME
export GATEWAY_URL=$GATEWAY_URL
export CORE_URL=$CORE_URL
export MYSQL_HOST=$MYSQL_HOST
export MYSQL_DB=$MYSQL_DB
export MYSQL_USER=$MYSQL_USER
export MYSQL_PASSWORD=$MYSQL_PASSWORD
ENV
  )
  # Copying over a deployed war makes Tomcat redeploy it, and the page 404s meanwhile.
  cmp -s web/status-page/target/status.war "$TOMCAT/webapps/status.war" || cp web/status-page/target/status.war "$TOMCAT/webapps/"
  ss -ltn | grep -q ':8080 ' || "$TOMCAT/bin/startup.sh" >/dev/null

  if [ ! -f "$RUN/php.pid" ] || ! kill -0 "$(cat "$RUN/php.pid")" 2>/dev/null; then
    (cd web/notes-uploader && exec nohup php -S 0.0.0.0:8070 -t public >"$RUN/php.log" 2>&1 </dev/null) &
    echo $! >"$RUN/php.pid"
  fi

  echo "waiting for the staff portal and status page..."
  for _ in $(seq 1 45); do
    curl -sf -m 2 -o /dev/null localhost:8085/actuator/health && curl -sf -m 2 -o /dev/null localhost:8080/status/ && break
    sleep 2
  done
  check
}

stop() {
  for f in staff php; do
    [ -f "$RUN/$f.pid" ] && kill "$(cat "$RUN/$f.pid")" 2>/dev/null
    rm -f "$RUN/$f.pid"
  done
  [ -x "$TOMCAT/bin/shutdown.sh" ] && { set_java; "$TOMCAT/bin/shutdown.sh"; } >/dev/null 2>&1
  # Tomcat exits a few seconds after shutdown.sh; start would otherwise find it still listening and skip it.
  for _ in $(seq 1 15); do ss -ltn | grep -q ':8080 ' || break; sleep 1; done
  echo "stopped"
}

probe() { curl -sf -m 4 -o /dev/null "$@"; }

check() {
  echo "This machine:"
  probe localhost:8085/actuator/health && pass "staff portal :8085" || fail "staff portal: tail $RUN/staff.log"
  probe localhost:8080/status/ && pass "status page :8080" || fail "status page: tail $TOMCAT/logs/catalina.out"
  probe localhost:8070/ && pass "notes uploader :8070" || fail "notes uploader: tail $RUN/php.log"
  probe localhost:8600/health && pass "resilience core :8600" || fail "resilience core: run make control-up"
  ss -ltn | grep -q ':3306 ' && pass "MySQL :3306" || fail "MySQL: sudo systemctl start mysqld"
  echo "The Mac ($PLATFORM_HOST):"
  probe "$GATEWAY_URL/api/status" && pass "gateway :8000" || fail "gateway: is scripts/demo.sh running, same network, right IP?"
  probe "$RAG_URL/health" && pass "RAG :8003" || fail "RAG: uploads will stay Pending"
  probe "http://$PLATFORM_HOST:3000/health" && pass "student portal :3000" || fail "student portal: allow node in the Mac's firewall"
  redis="$(curl -s -m 4 -H "X-CS-Token: $CS_TOKEN" "http://$PLATFORM_HOST:8002/control/state" || true)"
  case "$redis" in
    *'"control_source":"remote"'*|*'"control_source": "remote"'*) pass "the Mac follows this control room (token matches, heartbeat fresh)" ;;
    '') fail "orchestrator :8002 unreachable or CS_TOKEN differs" ;;
    *) fail "the Mac ignores this control room: check REDIS_PASSWORD and make control-up" ;;
  esac
  [ "$FAILS" = 0 ] && echo "ALL PASS" || echo "$FAILS problem(s)"
}

case "${1:-}" in
  setup) setup ;;
  start) start ;;
  stop) stop ;;
  check) check ;;
  *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
