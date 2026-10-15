#!/usr/bin/env bash
# Generuje małe bare repo udające Gerrita: refs/changes/XX/N/PS + fałszywe refy /meta (NoteDb).
# Deterministyczne daty -> powtarzalne SHA.
#
# Topologia (strzałka = "stoi na"):
#
#   master: base <- main1
#
#   1201/1 <- 1202/1 <- 1203/1        1203 stoi na STARYM PS 1202 -> nieaktualny
#         \<- 1202/2 (bieżący)
#         \<- 1204/1                  rozgałęzienie: 1202 i 1204 na tym samym rodzicu
#
#   7/1 <- 1234/1                     test shardów: refs/changes/07/7/1, refs/changes/34/1234/1
#
#   1300/1                            samotny CL
#   1500/1 na 1300/1, 1500/2 na main1 bieżący PS przerzucony na master -> 1500 NIE jest w łańcuchu z 1300
#
# Oczekiwane łańcuchy (tylko bieżące patch sety):
#   {1201, 1202, 1203, 1204}  1203 nieaktualny
#   {7, 1234}
#   {1300}
#   {1500}
set -euo pipefail

R=${1:-fixture.git}
rm -rf "$R"
git init -q --bare "$R"
cd "$R"

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
export GIT_AUTHOR_DATE='2026-01-01T00:00:00Z' GIT_COMMITTER_DATE='2026-01-01T00:00:00Z'

# mk <opis> [rodzic...] -> sha
mk() {
  local msg=$1; shift
  local blob tree cid args=()
  blob=$(printf '%s\n' "$msg" | git hash-object -w --stdin)
  tree=$(printf '100644 blob %s\tf\n' "$blob" | git mktree)
  for p in "$@"; do args+=(-p "$p"); done
  # Change-Id stały między patch setami tej samej zmiany (klucz = numer zmiany)
  cid=$(printf '%s' "${msg%%ps*}" | sha1sum | cut -c1-40)
  printf '%s\n\nChange-Id: I%s\n' "$msg" "$cid" | git commit-tree "$tree" "${args[@]}"
}

# ref <zmiana> <ps> <sha>
ref() {
  git update-ref "refs/changes/$(printf '%02d' $(($1 % 100)))/$1/$2" "$3"
}

# meta <zmiana> <grupa>  -- jeden commit NoteDb z footerami
EMPTY=$(git hash-object -t tree -w /dev/null)
meta() {
  local sha
  sha=$(printf 'Update patch set 1\n\nPatch-set: 1\nGroups: %s\n' "$2" | git commit-tree "$EMPTY")
  git update-ref "refs/changes/$(printf '%02d' $(($1 % 100)))/$1/meta" "$sha"
}

base=$(mk base)
m1=$(mk main1 "$base")
git update-ref refs/heads/master "$m1"
git symbolic-ref HEAD refs/heads/master

a1=$(mk 1201ps1 "$m1");   ref 1201 1 "$a1"
a2=$(mk 1202ps1 "$a1");   ref 1202 1 "$a2"
a3=$(mk 1203ps1 "$a2");   ref 1203 1 "$a3"
a2b=$(mk 1202ps2 "$a1");  ref 1202 2 "$a2b"
a4=$(mk 1204ps1 "$a1");   ref 1204 1 "$a4"

b1=$(mk 7ps1 "$m1");      ref 7 1 "$b1"
b2=$(mk 1234ps1 "$b1");   ref 1234 1 "$b2"

s=$(mk 1300ps1 "$m1");    ref 1300 1 "$s"
c1=$(mk 1500ps1 "$s");    ref 1500 1 "$c1"
c2=$(mk 1500ps2 "$m1");   ref 1500 2 "$c2"

for ch in 1201 1202 1203 1204; do meta "$ch" "$a1"; done
for ch in 7 1234;              do meta "$ch" "$b1"; done
meta 1300 "$s"
meta 1500 "$s"   # grupa z PS1 -- celowo nieaktualna podpowiedź, rodzice mówią co innego

git for-each-ref --format='%(objectname:short) %(refname)' refs/changes/
