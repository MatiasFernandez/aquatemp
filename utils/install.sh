#!/bin/sh
# Installs a test build of the Aqua Temp integration on Home Assistant, replacing the installed
# copy. Run it where the Home Assistant configuration folder is visible: the Terminal & SSH
# add-on, or the Home Assistant container. See docs/testing-in-home-assistant.md.
#
# The build is downloaded and checked before the installed copy is touched, so a failed download
# changes nothing, and each copy is made beside its destination before it replaces it, so a failed
# copy leaves the destination as it was. The installed copy is saved to aqua_temp.bak in the configuration folder, next
# to custom_components so Home Assistant doesn't load it. To go back to a release, redownload it
# in HACS, which replaces the whole folder.
#
# Keep it POSIX sh: in Home Assistant it runs on BusyBox.
set -eu

DOMAIN=aqua_temp
REPO=MatiasFernandez/aquatemp
# Where GitHub serves a ref's files as a .tar.gz, without a login; the tests point it elsewhere
CODELOAD=${AQUATEMP_CODELOAD:-https://codeload.github.com}

usage() {
	cat <<EOF
Usage: install.sh [options] <what>

What to install:
  pr <number>         a pull request
  ref <branch|sha>    a branch, tag or commit
  url <tarball>       a .tar.gz holding custom_components/$DOMAIN, such as utils/serve.py serves
  rollback            the copy that the last install replaced

Options:
  --config <path>     the Home Assistant configuration folder (default: the first of
                      /homeassistant and /config holding a configuration.yaml)
  --repo <owner/name> the GitHub repository for pr and ref (default: $REPO)
  --no-restart        don't restart Home Assistant afterwards
EOF
}

fail() {
	echo "install.sh: $*" >&2
	exit 1
}

find_config() {
	for dir in /homeassistant /config; do
		if [ -f "$dir/configuration.yaml" ]; then
			echo "$dir"
			return
		fi
	done
	fail "no configuration.yaml in /homeassistant or /config; pass --config <path>"
}

tarball_url() {
	case $1 in
	pr) echo "$CODELOAD/$REPO/legacy.tar.gz/refs/pull/$2/head" ;;
	ref) echo "$CODELOAD/$REPO/legacy.tar.gz/$2" ;;
	url) echo "$2" ;;
	esac
}

# Semantic version build metadata, which Home Assistant accepts in a manifest version and shows on
# the integration's page and in its diagnostics: the commit, as serve.py stamps a checkout. A pull
# request is stamped pr<number>.<commit>, and just pr<number> when the commit can't be read. A ref
# is left unstamped when it can't. A url build is stamped by whoever made it.
version_stamp() {
	case $1 in
	pr) echo "pr$2${3:+.$3}" ;;
	ref) echo "$3" ;;
	esac
}

# The commit a GitHub tarball holds, from the top folder its legacy.tar.gz names
# <owner>-<repo>-<commit>; nothing when the folder isn't named that way.
tarball_commit() {
	commit=${1##*-}
	case $commit in
	'' | *[!0-9a-f]*) ;;
	*) echo "$commit" ;;
	esac
}

download() {
	if command -v wget >/dev/null 2>&1; then
		wget -qO "$2" "$1"
	elif command -v curl >/dev/null 2>&1; then
		curl -fsSL -o "$2" "$1"
	else
		fail "neither wget nor curl is available"
	fi
}

manifest_version() {
	sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$1"
}

stamp_manifest() {
	sed "s/\(\"version\": *\"[^\"+]*\)[^\"]*\"/\1+$2\"/" "$1" >"$1.new"
	mv "$1.new" "$1"
}

# Copies $1 to $2 through a staging copy, so a failed copy leaves $2 as it was
replace() {
	rm -rf "$STAGING"
	if ! cp -R "$1" "$STAGING"; then
		rm -rf "$STAGING"
		fail "could not copy $1; $2 was left as it was"
	fi
	rm -rf "$2"
	mv "$STAGING" "$2"
}

restart() {
	if [ "$NO_RESTART" = 1 ]; then
		return
	fi
	if command -v ha >/dev/null 2>&1; then
		ha core restart
	else
		echo "Restart Home Assistant to load it: Settings > System > Power > Restart Home Assistant."
	fi
}

rollback() {
	[ -d "$BACKUP" ] || fail "no saved copy at $BACKUP"
	replace "$BACKUP" "$TARGET"
	echo "Restored version $(manifest_version "$TARGET/manifest.json") from $BACKUP."
	restart
}

install() {
	url=$(tarball_url "$MODE" "$ARG")
	work=$(mktemp -d)
	trap 'rm -rf "$work"' EXIT
	echo "Downloading $url"
	download "$url" "$work/build.tar.gz" || fail "could not download $url; nothing was changed"
	mkdir "$work/build"
	tar -xzf "$work/build.tar.gz" -C "$work/build" || fail "$url is not a .tar.gz; nothing was changed"

	# GitHub names the top folder after the commit, so it isn't known in advance
	source=
	for manifest in "$work"/build/*/custom_components/"$DOMAIN"/manifest.json; do
		[ -f "$manifest" ] && source=$(dirname "$manifest")
	done
	[ -n "$source" ] || fail "$url holds no custom_components/$DOMAIN; nothing was changed"
	top=$(basename "$(dirname "$(dirname "$source")")")
	stamp=$(version_stamp "$MODE" "$ARG" "$(tarball_commit "$top")")
	if [ -n "$stamp" ]; then
		stamp_manifest "$source/manifest.json" "$stamp"
	fi

	mkdir -p "$CONFIG/custom_components"
	if [ -d "$TARGET" ]; then
		replace "$TARGET" "$BACKUP"
		echo "Saved the installed version $(manifest_version "$TARGET/manifest.json") to $BACKUP."
	fi
	replace "$source" "$TARGET"
	echo "Installed version $(manifest_version "$TARGET/manifest.json") into $TARGET."
	echo "To go back, redownload your version in HACS, or run install.sh rollback."
	restart
}

CONFIG=
MODE=
ARG=
NO_RESTART=0
while [ $# -gt 0 ]; do
	case $1 in
	--config)
		[ $# -ge 2 ] || fail "--config needs a path"
		CONFIG=$2
		shift
		;;
	--repo)
		[ $# -ge 2 ] || fail "--repo needs an owner/name"
		REPO=$2
		shift
		;;
	--no-restart) NO_RESTART=1 ;;
	-h | --help)
		usage
		exit 0
		;;
	-*) fail "unknown option $1; see install.sh --help" ;;
	*)
		if [ -z "$MODE" ]; then
			MODE=$1
		elif [ -z "$ARG" ]; then
			ARG=$1
		else
			fail "unexpected argument $1; see install.sh --help"
		fi
		;;
	esac
	shift
done

case $MODE in
pr) case $ARG in '' | *[!0-9]*) fail "pr needs a pull request number" ;; esac ;;
ref | url) [ -n "$ARG" ] || fail "$MODE needs a value; see install.sh --help" ;;
rollback) [ -z "$ARG" ] || fail "rollback takes no value" ;;
'')
	usage >&2
	exit 2
	;;
*) fail "unknown command $MODE; see install.sh --help" ;;
esac

if [ -n "$CONFIG" ]; then
	[ -f "$CONFIG/configuration.yaml" ] || fail "no configuration.yaml in $CONFIG"
else
	CONFIG=$(find_config)
fi
TARGET=$CONFIG/custom_components/$DOMAIN
BACKUP=$CONFIG/$DOMAIN.bak
# Outside custom_components, so Home Assistant never loads a half-made copy
STAGING=$CONFIG/$DOMAIN.new

if [ "$MODE" = rollback ]; then
	rollback
else
	install
fi
