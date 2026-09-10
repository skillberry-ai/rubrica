#!/usr/bin/env bash
#
# release-notes.sh — build markdown release notes from Conventional Commit
# subjects in a git range. Sourced by scripts/release.sh.
#
# Not executable on its own and deliberately free of side effects: it only
# reads git history and writes to stdout, which is what makes it testable.
# Sourced-only: deliberately sets no shell options, since that would affect
# the caller's shell.

# Commit types, in the order their sections appear in the notes.
RELEASE_NOTES_TYPES=(feat fix perf refactor docs test build ci chore)

# release_notes_heading <type> — section heading for a commit type.
release_notes_heading() {
    case "$1" in
        feat)     printf 'Features\n' ;;
        fix)      printf 'Fixes\n' ;;
        perf)     printf 'Performance\n' ;;
        refactor) printf 'Refactoring\n' ;;
        docs)     printf 'Documentation\n' ;;
        test)     printf 'Tests\n' ;;
        build)    printf 'Build\n' ;;
        ci)       printf 'CI\n' ;;
        chore)    printf 'Chores\n' ;;
        breaking) printf 'Breaking changes\n' ;;
        *)        printf 'Other\n' ;;
    esac
}

# _release_notes_scrub_citations <text> — strip internal-tracker citations from
# text bound for CHANGELOG.md, printing the result.
#
# Why this exists, measured: cutting v0.1.0 put nine tracker citations into
# CHANGELOG.md across seven bullets, carried in verbatim from subjects written
# before the tree's citations were rewritten, and tests/unit/test_docs_accuracy.py
# failed on main. They are not reproduced here, because this file is scanned by
# that same guard -- listing them to explain the fix is how the first draft of
# this comment failed it. The generator and that guard
# were each correct alone: subjects are meant to reach a section as written, and
# _GENERATED_ROOT_DOCS keeps CHANGELOG.md inside the citation guard on purpose
# ("a stale count in a changelog section is a record, a tracker citation there is
# a broken pointer"). Nothing had measured them together, because nothing had
# been released. History is immutable, so the generator is the only place a fix
# can live.
#
# The four patterns mirror _TRACKER_CITATION and _TRACKER_CITATION_BARE in that
# module. They are duplicated here rather than shared because the guard is Python
# and this is sourced bash; the test added alongside this function asserts the two
# stay in agreement, which is what makes the duplication safe.
#
# Deletion, not substitution, and the choice is deliberate. Substituting a neutral
# phrase reads worse in the cases that actually occur: a subject where the citation
# sits between an article and a noun turns into "a an internal issue docstring".
# Deleting can leave clipped prose instead -- the
# accepted cost, because the real remedy is upstream and docs/releasing.md already
# states it: "write the subject you would want to read there." A clipped bullet is
# a cosmetic defect; a live pointer to an unrelated public issue is a wrong one.
_release_notes_scrub_citations() {
    printf '%s' "$1" | sed -E \
        -e 's/\(#[0-9]+\)//g' \
        -e "s/#[0-9]+'s\\b//g" \
        -e 's/\b[Ii]ssues?[[:space:]]+#?[0-9]+\b//g' \
        -e 's/\bPR[[:space:]]+#[0-9]+\b//g' \
        -e 's/#[0-9]+//g' \
        -e 's/[[:space:]]+,/,/g' \
        -e 's/,([[:space:]]*,)+/,/g' \
        -e 's/[[:space:]]{2,}/ /g' \
        -e 's/[[:space:]]+([.,;:])/\1/g' \
        -e 's/(^|[[:space:]])(and|after)[[:space:]]*,[[:space:]]*/\1/g' \
        -e 's/[[:space:]]+$//' \
        -e 's/^[[:space:]]+//'
}

# _release_notes_is_conventional <subject> — true when the subject opens with a
# known type, an optional (scope), an optional ! and a colon.
_release_notes_is_conventional() {
    local subject="$1" type
    for type in "${RELEASE_NOTES_TYPES[@]}"; do
        if [[ "$subject" =~ ^"$type"(\([^\)]*\))?!?: ]]; then
            return 0
        fi
    done
    return 1
}

# _release_notes_breaking_footer <sha> — the prose of a `BREAKING CHANGE:` (or
# `BREAKING-CHANGE:`) footer, folded onto one line, or empty when there is none.
# Folding matters because the footer is usually wrapped across several lines but
# has to become one markdown bullet.
#
# Collection stops at a blank line *or* at a trailer-shaped line, and the second
# condition is the load-bearing one: `BREAKING-CHANGE:` — the hyphenated spelling
# the regex below accepts — is itself a valid git trailer token, so `git commit
# -s` appends `Signed-off-by:` directly beneath it with no blank line between.
# On a blank-line-only stop the fold then swallowed that trailer, and the
# mandated `Assisted-By:` with it, into a bullet that ships in the GitHub Release
# and in the committed CHANGELOG.md. The token pattern is git's own
# (`[A-Za-z0-9-]+:` then a space or end of line), so what we stop at is exactly
# what git would have treated as a trailer when it wrote the message.
#
# A wrapped continuation line that happens to open `Word: ...` stops collection
# too, truncating the prose. That is accepted deliberately: the format itself
# cannot distinguish the two cases — git would read such a line as a trailer as
# well — and truncated prose is a far better failure than a committer's name and
# email leaking into a public changelog.
_release_notes_breaking_footer() {
    git show -s --format='%B' "$1" | awk '
        !done_one && /^BREAKING[ -]CHANGE:/ {
            sub(/^BREAKING[ -]CHANGE:[[:space:]]*/, "")
            buf = $0; collecting = 1; next
        }
        collecting {
            if ($0 ~ /^[[:space:]]*$/) { collecting = 0; done_one = 1; next }
            if ($0 ~ /^[A-Za-z0-9-]+:([[:space:]]|$)/) { collecting = 0; done_one = 1; next }
            buf = buf " " $0
        }
        END {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", buf)
            if (buf != "") print buf
        }
    '
}

# generate_release_notes <range> — print markdown notes for <range>, grouped by
# type in RELEASE_NOTES_TYPES order with unparseable subjects under "Other".
# Merge commits are excluded. Prints nothing for an empty range.
generate_release_notes() {
    local range="$1"
    local type heading subject scope desc sha footer bang text i
    local -a subjects=() shas=() bucket=() breaking=()

    mapfile -t subjects < <(git log --no-merges --reverse --format='%s' "$range")
    (( ${#subjects[@]} )) || return 0
    mapfile -t shas < <(git log --no-merges --reverse --format='%H' "$range")

    # Scrubbed here, once, before anything parses a subject: the conventional-commit
    # prefix cannot contain a citation, so stripping first cannot disturb the type,
    # scope or `!` the loops below match -- and doing it at the single point where
    # subjects enter covers every bullet, the "Other" bucket included, rather than
    # at each of the places one is printed.
    for i in "${!subjects[@]}"; do
        subjects[i]="$(_release_notes_scrub_citations "${subjects[$i]}")"
    done

    # Breaking changes lead the notes: they are the only entries a reader has to
    # act on before upgrading. A commit declares one either with `!` before the
    # colon or with a BREAKING CHANGE footer. When a footer is present its prose
    # wins, because it says what the reader must *do*, whereas the subject only
    # says what changed. Breaking commits still appear under their own type
    # below, so this section adds emphasis without removing anything.
    for i in "${!subjects[@]}"; do
        subject="${subjects[$i]}"
        sha="${shas[$i]}"
        footer="$(_release_notes_breaking_footer "$sha")"
        # The footer is body prose, not a subject, so it bypasses the scrub above
        # and needs its own. A BREAKING CHANGE footer is exactly the place a commit
        # explains itself by pointing at an issue, so this is not a hypothetical.
        footer="$(_release_notes_scrub_citations "$footer")"
        scope=""
        bang=""
        desc="$subject"
        # Matched inline rather than via a helper returning joined fields: tab is
        # an IFS whitespace character, so `read` would collapse the empty scope
        # and `!` fields and shift the description into the wrong variable.
        for type in "${RELEASE_NOTES_TYPES[@]}"; do
            if [[ "$subject" =~ ^"$type"(\([^\)]*\))?(!)?:[[:space:]]*(.*)$ ]]; then
                scope="${BASH_REMATCH[1]}"
                scope="${scope#(}"
                scope="${scope%)}"
                bang="${BASH_REMATCH[2]}"
                desc="${BASH_REMATCH[3]}"
                break
            fi
        done
        [[ -n "$bang" || -n "$footer" ]] || continue
        if [[ -n "$footer" ]]; then
            text="$footer"
        else
            text="$desc"
        fi
        if [[ -n "$scope" ]]; then
            breaking+=("**${scope}:** ${text}")
        else
            breaking+=("$text")
        fi
    done

    if (( ${#breaking[@]} )); then
        printf '### %s\n\n' "$(release_notes_heading breaking)"
        printf -- '- %s\n' "${breaking[@]}"
        printf '\n'
    fi

    for type in "${RELEASE_NOTES_TYPES[@]}" other; do
        bucket=()
        for subject in "${subjects[@]}"; do
            if [[ "$type" == other ]]; then
                if ! _release_notes_is_conventional "$subject"; then
                    bucket+=("$subject")
                fi
                continue
            fi
            if [[ "$subject" =~ ^"$type"(\([^\)]*\))?!?:[[:space:]]*(.*)$ ]]; then
                scope="${BASH_REMATCH[1]}"
                desc="${BASH_REMATCH[2]}"
                scope="${scope#(}"
                scope="${scope%)}"
                if [[ -n "$scope" ]]; then
                    bucket+=("**${scope}:** ${desc}")
                else
                    bucket+=("$desc")
                fi
            fi
        done
        (( ${#bucket[@]} )) || continue
        heading="$(release_notes_heading "$type")"
        printf '### %s\n\n' "$heading"
        printf -- '- %s\n' "${bucket[@]}"
        printf '\n'
    done
}
