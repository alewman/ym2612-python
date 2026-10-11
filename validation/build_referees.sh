#!/bin/sh
# Build the two FM referees from the pinned die-derived sources in reference/src/
# (fetched by scripts/fetch_references.py, never committed here).
#
#   sh validation/build_referees.sh
#
# The binaries land in reference/build-referees/ (git-ignored).  Nothing of the
# referees' source is copied into this repository: validation/*.c only drive them.
#
# Licences: Nuked-OPN2 LGPL-2.1, YM2608-LLE GPL-2.0.  The binaries are built locally
# and run as referees; they are not distributed.
set -e
root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/reference/src"
out="$root/reference/build-referees"
mkdir -p "$out"

CC=${CC:-gcc}
CFLAGS=${CFLAGS:--O2 -w}
$CC --version | head -n 1

echo "opn2_ref  (Nuked-OPN2 @ 335747d)"
$CC $CFLAGS -I "$src/Nuked-OPN2" -o "$out/opn2_ref" \
    "$root/validation/opn2_ref.c" "$src/Nuked-OPN2/ym3438.c"

echo "lle2612_ref (YM2608-LLE @ 7a2aca7, fmopna_2612.c)"
$CC $CFLAGS -I "$src/YM2608-LLE" -o "$out/lle2612_ref" \
    "$root/validation/lle2612_ref.c" "$src/YM2608-LLE/fmopna_2612.c"

echo "built in $out"
