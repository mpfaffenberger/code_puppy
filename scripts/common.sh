# Common functions for shell scripts
# usage:
# source $SCRIPTS_DIR/common.sh

# shellcheck disable=SC2034
bail () {
  exit 0;
}

show_help() {
    echo; echo "$HEADER"|grep -e "^#" | sed -e "s/^#[%+-]*//g" -e "s/\$0/$SELF/g"; echo; exit 0
}

usage() {
    echo "$HEADER"|grep -e "^#[%+-]" | sed -e "s/^#[%+-]//g" -e "s/\$0/$SELF/g"
}

bail_with_error () {
  echo; echo "ERROR: $1"; echo; exit "${2-1}";
}

bail_with_usage () {
  echo; echo "ERROR: $1"; usage; exit "${2-1}";
}

error_handler () {
  local ret="$1"
  local message="$2"
  if (( ret )); then
    echo "🚫 ERROR: $message"
    exit 101
  else
    echo "✅ OK"
  fi
}

set_param () {
  # shellcheck disable=SC2086
  {
    local var="$1"
    local val=${2-"##undef##"}
    eval $var=$val
    [[ ${!var} == -* ]] && eval $var="##undef##"
    #echo "val: ${!var}"
  }
}

spinner_start() {
  spinner_symbols=( "|" "/" "-" "\\" )
  current_symbol=0

  while true; do
    echo -ne "\r${spinner_symbols[$current_symbol]}"
    (( current_symbol = (current_symbol + 1) % ${#spinner_symbols[@]} ))
    sleep 0.2
  done
}

spinner_stop() {
  local pid="$1"
  kill "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  echo -ne "\r"
}

sleepSpinner() {
  local interval="$1"
  local pid=""
  spinner_start &
  pid=$!
  sleep "$interval"
  spinner_stop $pid
}
