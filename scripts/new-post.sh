#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COLLECTIONS=("lifelogs" "guides")
MONTHS=("Jan" "Feb" "Mar" "Apr" "May" "Jun" "Jul" "Aug" "Sep" "Oct" "Nov" "Dec")

slugify() {
    printf '%s\n' "$1" |
        tr '[:upper:]' '[:lower:]' |
        sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

format_pub_date() {
    local date_str="$1"

    local month
    local day
    local year

    month=$(date -d "$date_str" +%m)
    day=$(date -d "$date_str" +%d)
    year=$(date -d "$date_str" +%Y)

    printf '%s %s %s\n' "${MONTHS[10#$month - 1]}" "$day" "$year"
}

is_valid_collection() {
    case "$1" in
        lifelogs|guides)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

parse_args() {
    local collection="$1"
    local title="$2"
    local description=""
    local -a tags=()

    shift 2

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --description)
                if [[ $# -lt 2 ]]; then
                    echo "Error: --description requires a value" >&2
                    exit 1
                fi

                description="$2"
                shift 2
                ;;

            --tags)
                if [[ $# -lt 2 ]]; then
                    echo "Error: --tags requires a comma-separated value" >&2
                    exit 1
                fi

                IFS=',' read -r -a tags <<< "$2"
                shift 2
                ;;

            *)
                echo "Error: Unknown argument: $1" >&2
                exit 1
                ;;
        esac
    done

    printf 'collection=%q\n' "$collection"
    printf 'title=%q\n' "$title"
    printf 'description=%q\n' "$description"
    printf 'tags=('

    printf '%q ' "${tags[@]}"

    printf ')\n'
}

main() {
    local collection=""
    local title=""
    local description=""
    local tags_input=""
    local -a tags=()

    if [[ $# -ge 2 ]] && is_valid_collection "$1"; then
        eval "$(parse_args "$@")"
    else
        echo "📝 Create new post"
        echo

        while true; do
            read -rp "Collection (lifelogs/guides): " collection

            if is_valid_collection "$collection"; then
                break
            fi

            echo "Please choose: lifelogs or guides"
        done

        while true; do
            read -rp "Title: " title

            if [[ -n "$title" ]]; then
                break
            fi

            echo "Title is required"
        done

        read -rp "Description (optional): " description
        read -rp "Tags (comma-separated, optional): " tags_input

        if [[ -n "$tags_input" ]]; then
            IFS=',' read -r -a tags <<< "$tags_input"
        fi
    fi

    if [[ -z "$collection" || -z "$title" ]]; then
        echo "Error: Collection and title are required." >&2
        exit 1
    fi

    if ! is_valid_collection "$collection"; then
        echo "Error: Invalid collection: $collection" >&2
        exit 1
    fi

    local date_str
    local slug
    local filename
    local content_dir
    local filepath
    local pub_date

    date_str=$(date +%F)
    slug=$(slugify "$title")
    filename="${date_str}-${slug}.md"

    content_dir="$ROOT/src/content/$collection"
    filepath="$content_dir/$filename"
    pub_date=$(format_pub_date "$date_str")

    if [[ ! -d "$content_dir" ]]; then
        echo "Error: Collection directory not found: $content_dir" >&2
        exit 1
    fi

    if [[ -f "$filepath" ]]; then
        echo "Error: File already exists: $filepath" >&2
        exit 1
    fi

    {
        printf '%s\n' "---"
        printf 'title: %s\n' "$(printf '%q' "$title")"
        printf 'description: %s\n' "$(printf '%q' "$description")"
        printf "pubDate: '%s'\n" "$pub_date"

        if [[ ${#tags[@]} -gt 0 ]]; then
            printf '%s\n' "tags:"

            for tag in "${tags[@]}"; do
                # Remove accidental whitespace around comma-separated tags.
                tag="$(printf '%s' "$tag" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"

                [[ -z "$tag" ]] && continue

                printf '  - %s\n' "$(printf '%q' "$tag")"
            done
        fi

        printf '%s\n' "---"
        printf '\n'
        printf '# %s\n' "$title"
        printf '\n'
        printf '%s\n' "Write your content here..."
    } > "$filepath"

    echo "✅ Created: $filepath"
}

main "$@"