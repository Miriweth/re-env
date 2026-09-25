# Template rendering. Source after lib/common.sh.
# shellcheck shell=bash

# render_template SRC DEST — replace @RE_HOME@ with the current RE_HOME.
render_template() {
    mkdir -p "$(dirname "$2")"
    sed "s|@RE_HOME@|$RE_HOME|g" "$1" > "$2"
}
