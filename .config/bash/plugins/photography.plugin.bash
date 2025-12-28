cite about-plugin
about-plugin 'useful tools for photographers'

# use SetFile and exiftool to set the file creation date from EXIF metadata
# requires: xcode-select and exiftool
function fix_date_from_exif() {
  if [ $# -eq 0 ]; then
    echo "Usage: fix_date_from_exif <file>..." >&2
    return 1
  fi

  local f d failed=0

  for f in "$@"; do
    if [ ! -f "$f" ]; then
      echo "File not found: $f" >&2
      ((failed++))
      continue
    fi

    d="$(exiftool -s3 -d '%m/%d/%Y %H:%M:%S' -DateTimeOriginal "$f")" || {
      echo "exiftool failed for $f" >&2
      ((failed++))
      continue
    }

    [ -z "$d" ] && {
      echo "No DateTimeOriginal in EXIF for $f" >&2
      ((failed++))
      continue
    }

    if SetFile -d "$d" "$f"; then
      echo "Fixed $f to $d"
    else
      echo "SetFile failed for $f" >&2
      ((failed++))
    fi
  done

  [ "$failed" -gt 0 ] && return 1
}

# use exiftool to remove all metadata except copyright information
function keep_copyright_only() {
  if [ $# -eq 0 ]; then
    echo "Usage: keep_copyright_only <file> [file ...] or keep_copyright_only <glob_pattern>" >&2
    echo "Examples:" >&2
    echo "  keep_copyright_only image1.jpg image2.jpg" >&2
    echo "  keep_copyright_only '*.jpg'" >&2
    return 1
  fi

  local f glob_pattern files
  local tmp_args tmp_icc orig_created

  # Handle glob pattern vs direct files
  if [ $# -eq 1 ] && [[ "$1" == *"*"? ]]; then
    # First argument looks like a glob pattern
    glob_pattern="$1"
    if ! files=("$@"); then
      echo "Error: Failed to expand glob pattern '$glob_pattern'" >&2
      return 1
    fi
  else
    # Direct file arguments
    files=("$@")
  fi

  # Validate all files exist and are readable
  local valid_files=()
  for f in "${files[@]}"; do
    if [ -r "$f" ] && [ -f "$f" ]; then
      valid_files+=("$f")
    else
      echo "Warning: Skipping '$f' - not a readable file" >&2
    fi
  done

  if [ ${#valid_files[@]} -eq 0 ]; then
    echo "Error: No valid files to process" >&2
    return 1
  fi

  # Process each file
  local failed=0
  for f in "${valid_files[@]}"; do
    echo "Processing: $f"

    tmp_args="$(mktemp /tmp/metaargsXXXXXX)" || {
      ((failed++))
      continue
    }
    tmp_icc="$(mktemp /tmp/iccXXXXXX.icc)" || {
      rm -f "$tmp_args"
      ((failed++))
      continue
    }

    # 0) Save original creation date (filesystem)
    if ! orig_created="$(GetFileInfo -d "$f")"; then
      echo "Warning: Failed to get creation date for '$f', skipping date restoration" >&2
      rm -f "$tmp_args" "$tmp_icc"
      ((failed++))
      continue
    fi

    # 1) Export only the tags we want to keep as exiftool args
    if ! exiftool -args \
      -DateTimeOriginal \
      -CreateDate \
      -ModifyDate \
      -Copyright \
      -XMP-dc:Rights \
      -IPTC:CopyrightNotice \
      "$f" >"$tmp_args" 2>/dev/null; then
      echo "Warning: Failed to extract metadata from '$f'" >&2
      rm -f "$tmp_args" "$tmp_icc"
      ((failed++))
      continue
    fi

    # 2) Extract ICC profile (if any)
    exiftool -icc_profile -b "$f" >"$tmp_icc" 2>/dev/null

    # 3) Nuke all metadata
    if ! exiftool -overwrite_original -all= "$f" >/dev/null 2>&1; then
      echo "Error: Failed to remove metadata from '$f'" >&2
      rm -f "$tmp_args" "$tmp_icc"
      ((failed++))
      continue
    fi

    # 4) Re-embed ICC profile
    if [ -s "$tmp_icc" ]; then
      exiftool -overwrite_original "-ICC_Profile<=$tmp_icc" "$f" >/dev/null 2>&1 ||
        echo "Warning: Failed to restore ICC profile for '$f'" >&2
    fi

    # 5) Reapply saved metadata (including capture date)
    if [ -s "$tmp_args" ]; then
      exiftool -overwrite_original -@ "$tmp_args" "$f" >/dev/null 2>&1 ||
        echo "Warning: Failed to restore metadata for '$f'" >&2
    fi

    # 6) Restore original file creation date (filesystem)
    if ! SetFile -d "$orig_created" "$f" 2>/dev/null; then
      echo "Warning: Failed to restore creation date for '$f'" >&2
    fi

    rm -f "$tmp_args" "$tmp_icc"
    echo "✓ Done: $f"
  done

  if [ $failed -gt 0 ]; then
    echo "Completed with $failed failures out of ${#valid_files[@]} files" >&2
    return $((failed > 0))
  fi

  echo "✓ Successfully processed ${#valid_files[@]} files"
}

##############################################################################
# fix_date_from_name - Synchronize EXIF datetime with filename timestamp
#
# Compares datetime extracted from photo filenames (YYYYMMDD_HHmmSS format)
# with EXIF metadata datetime fields and provides interactive correction.
#
# Usage:
#   fix_date_from_name [DIRECTORY] [GLOB_PATTERN]
#
# Arguments:
#   DIRECTORY     - Directory containing photos (default: current directory)
#   GLOB_PATTERN  - Optional glob pattern to filter files (e.g., "ext-*")
#
# Examples:
#   fix_date_from_name
#   fix_date_from_name /path/to/photos
#   fix_date_from_name /path/to/photos "ext-*"
#   fix_date_from_name . "*.jpg"
#
##############################################################################
function fix_date_from_name() {
    local target_dir="${1:-.}"
    local glob_pattern="${2:-./*}"
    local files_to_process=()
    local decision_all=""
    local timestamp_regex='[0-9]{8}_[0-9]{6}'

    if ! command -v exiftool &>/dev/null; then
        echo "Error: exiftool is not installed." >&2
        return 1
    fi

    if [[ ! -d "$target_dir" ]]; then
        echo "Error: Directory '$target_dir' does not exist." >&2
        return 1
    fi

    if [[ "$2" == "" ]]; then
        glob_pattern="${target_dir}/*"
    else
        glob_pattern="${target_dir}/${glob_pattern}"
    fi

    echo "📸 Photo Metadata Synchronizer"
    echo "================================"
    echo "Directory: $target_dir"
    echo "Pattern: $glob_pattern"
    echo ""

    for file in $glob_pattern; do
        [[ ! -f "$file" ]] && continue
        local filename
        filename=$(basename "$file")
        if [[ $filename =~ $timestamp_regex ]]; then
            files_to_process+=("$file")
        fi
    done

    if [[ ${#files_to_process[@]} -eq 0 ]]; then
        echo "No files found with YYYYMMDD_HHmmSS timestamp in filename."
        return 0
    fi

    echo "Found ${#files_to_process[@]} file(s) with timestamp in filename."
    echo ""

    local file_count=0
    for file in "${files_to_process[@]}"; do
        ((file_count++))
        _fix_date_from_name_process_file "$file" "$file_count" "${#files_to_process[@]}"
    done

    echo ""
    echo "✅ Processing complete!"
}

function _fix_date_from_name_extract_datetime() {
    local filename="$1"
    local timestamp_regex='([0-9]{4})([0-9]{2})([0-9]{2})_([0-9]{2})([0-9]{2})([0-9]{2})'

    if [[ $filename =~ $timestamp_regex ]]; then
        local year="${BASH_REMATCH[1]}"
        local month="${BASH_REMATCH[2]}"
        local day="${BASH_REMATCH[3]}"
        local hour="${BASH_REMATCH[4]}"
        local minute="${BASH_REMATCH[5]}"
        local second="${BASH_REMATCH[6]}"
        echo "${year}:${month}:${day} ${hour}:${minute}:${second}"
        return 0
    fi
    return 1
}

function _fix_date_from_name_get_exif_datetime() {
    local file="$1"
    local exif_datetime

    exif_datetime=$(exiftool -s -s -s -DateTimeOriginal "$file" 2>/dev/null)
    if [[ -z "$exif_datetime" || "$exif_datetime" == "-" ]]; then
        exif_datetime=$(exiftool -s -s -s -CreateDate "$file" 2>/dev/null)
    fi
    if [[ -z "$exif_datetime" || "$exif_datetime" == "-" ]]; then
        exif_datetime=$(exiftool -s -s -s -FileModifyDate "$file" 2>/dev/null)
    fi
    if [[ -z "$exif_datetime" || "$exif_datetime" == "-" ]]; then
        echo "NOT SET"
        return 1
    fi
    echo "$exif_datetime"
    return 0
}

function _fix_date_from_name_prompt_user() {
    local filename="$1"
    local filename_dt="$2"
    local exif_dt="$3"
    local file_num="$4"
    local total_files="$5"

    printf "\n"
    printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    printf "[%d/%d] %s\n" "$file_num" "$total_files" "$filename"
    printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    printf "Filename datetime:  %s\n" "$filename_dt"
    printf "EXIF datetime:      %s\n" "$exif_dt"
    printf "\nDo you want to update EXIF to match filename?\n\n"
    printf "Options:\n"
    printf "  [y] Yes     - Update this file\n"
    printf "  [n] No      - Keep original EXIF\n"
    printf "  [Y] Yes ALL - Update all remaining files\n"
    printf "  [N] No ALL  - Keep original for all remaining files\n"
    printf "  [s] Skip    - Skip this file\n"

    read -r -p "Choice: " -n 1 choice
    echo ""

    case "$choice" in
        [yY])
            [[ "$choice" == "Y" ]] && return 3 || return 1
            ;;
        [nN])
            [[ "$choice" == "N" ]] && return 2 || return 0
            ;;
        [sS])
            return 4
            ;;
        *)
            echo "Invalid choice. Skipping file."
            return 4
            ;;
    esac
}

function _fix_date_from_name_update_exif() {
    local file="$1"
    local new_datetime="$2"

    if exiftool -q -overwrite_original \
        -DateTimeOriginal="$new_datetime" \
        -CreateDate="$new_datetime" \
        "$file" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

function _fix_date_from_name_process_file() {
    local file="$1"
    local file_num="$2"
    local total_files="$3"
    local filename
    filename=$(basename "$file")

    local filename_dt
    filename_dt=$(_fix_date_from_name_extract_datetime "$filename") || {
        echo "Error: Could not extract datetime from filename: $filename" >&2
        return 1
    }

    local exif_dt
    exif_dt=$(_fix_date_from_name_get_exif_datetime "$file")

    if [[ "$filename_dt" == "$exif_dt" ]]; then
        return 0
    fi

    if [[ -n "$decision_all" ]]; then
        if [[ "$decision_all" == "change" ]]; then
            echo "[$file_num/$total_files] Updating: $filename"
            _fix_date_from_name_update_exif "$file" "$filename_dt" || {
                echo "  ⚠️  Failed to update EXIF for: $filename" >&2
            }
        elif [[ "$decision_all" == "keep" ]]; then
            echo "[$file_num/$total_files] Keeping original: $filename"
        fi
    else
        _fix_date_from_name_prompt_user "$filename" "$filename_dt" "$exif_dt" "$file_num" "$total_files"
        local user_choice=$?

        case $user_choice in
            0)
                echo "  ✓ Keeping original EXIF datetime"
                ;;
            1)
                echo "  ✓ Updating EXIF datetime..."
                _fix_date_from_name_update_exif "$file" "$filename_dt" && {
                    echo "  ✅ Updated successfully"
                } || {
                    echo "  ❌ Failed to update EXIF" >&2
                }
                ;;
            2)
                decision_all="keep"
                echo "  ✓ Will keep original for remaining files"
                ;;
            3)
                decision_all="change"
                echo "  ✓ Updating EXIF datetime..."
                _fix_date_from_name_update_exif "$file" "$filename_dt" && {
                    echo "  ✅ Updated successfully"
                } || {
                    echo "  ❌ Failed to update EXIF" >&2
                }
                ;;
            4)
                echo "  ⊘ Skipped"
                ;;
        esac
    fi
}
