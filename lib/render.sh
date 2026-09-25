# Template rendering. Source after lib/common.sh.
# shellcheck shell=bash

# render_template SRC DEST — replace @RE_HOME@ with the current RE_HOME.
# Plain bash substitution, so |, & and \ in the path need no escaping. The
# replacement is quoted because bash 5.2 otherwise treats & as "the match".
render_template() {
    local content
    content="$(<"$1")"
    mkdir -p "$(dirname "$2")"
    printf '%s\n' "${content//@RE_HOME@/"$RE_HOME"}" > "$2"
}
