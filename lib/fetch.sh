# Verified downloads and extraction. Source after lib/common.sh.
# shellcheck shell=bash

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

# fetch_verified URL SHA256 DEST — download once, verify, never leave a half file behind.
fetch_verified() {
    local url="$1" sha="$2" dest="$3"
    if [[ -f "$dest" && "$(sha256_of "$dest")" == "$sha" ]]; then
        echo "present: $dest"
        return 0
    fi
    mkdir -p "$(dirname "$dest")"
    echo "fetching: $url"
    curl -fsSL -o "$dest.part" "$url" || { rm -f "$dest.part"; die "download failed: $url"; }
    if [[ "$(sha256_of "$dest.part")" != "$sha" ]]; then
        rm -f "$dest.part"
        die "checksum mismatch for $url (see versions.env)"
    fi
    mv "$dest.part" "$dest"
}

# extract_zip ZIP DIR — unpack, overwriting silently.
extract_zip() {
    need unzip
    mkdir -p "$2"
    unzip -oq "$1" -d "$2"
}
