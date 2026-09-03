#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <section> [title]"
  echo ""
  echo "  section   lifelogs or guides"
  echo "  title     post title (optional, will prompt if omitted)"
  echo "  tags      comma-separated tags (optional, will prompt if omitted)"
  exit 1
}

[ $# -lt 1 ] && usage

SECTION="$1"
TITLE="${2:-}"
TAGS="${3:-}"

if [ "$SECTION" != "lifelogs" ] && [ "$SECTION" != "guides" ]; then
  echo "Error: section must be 'lifelogs' or 'guides'"
  exit 1
fi

if [ -z "$TITLE" ]; then
  read -rp "Post title: " TITLE
fi

if [ -z "$TITLE" ]; then
  echo "Error: title cannot be empty"
  exit 1
fi

if [ -z "$TAGS" ]; then
  read -rp "Tags (comma-separated): " TAGS
fi

DATE=$(date +%Y-%m-%d)
SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//' | sed 's/-$//')

POSTS_DIR="docs/${SECTION}/posts"
mkdir -p "$POSTS_DIR"

FILE="${POSTS_DIR}/${SLUG}.md"

if [ -f "$FILE" ]; then
  echo "Error: ${FILE} already exists"
  exit 1
fi

TAG_ARRAY=""
if [ -n "$TAGS" ]; then
  TAG_ARRAY=$(echo "$TAGS" | awk -F',' '{
    for (i=1; i<=NF; i++) {
      gsub(/^[ \t]+|[ \t]+$/, "", $i)
      if ($i != "") printf "  - %s\n", $i
    }
  }')
else
  TAG_ARRAY="  - "
fi

cat > "$FILE" << TEMPLATE
---
title: TITLE_PLACEHOLDER
date: DATE_PLACEHOLDER
description: ""
tags:
TAG_ARRAY_PLACEHOLDER
---

# {{ \$frontmatter.title }}

### {{ new Date(\$frontmatter.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }}

TEMPLATE

sed -i "s|TITLE_PLACEHOLDER|${TITLE}|" "$FILE"
sed -i "s|DATE_PLACEHOLDER|${DATE}|" "$FILE"
sed -i "s|TAG_ARRAY_PLACEHOLDER|${TAG_ARRAY}|" "$FILE"

echo "Created: ${FILE}"
