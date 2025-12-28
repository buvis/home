cite about-plugin
about-plugin 'functions for development'

function tbump-patch() {
  local current
  current=$(tbump current-version)
  local major
  major=$(echo "$current" | cut -d. -f1)
  local minor
  minor=$(echo "$current" | cut -d. -f2)
  local patch
  patch=$(echo "$current" | cut -d. -f3)
  local next
  next="$major.$minor.$((patch + 1))"
  tbump "$next"
}

function tbump-minor() {
  local current
  current=$(tbump current-version)
  local major
  major=$(echo "$current" | cut -d. -f1)
  local minor
  minor=$(echo "$current" | cut -d. -f2)
  local next
  next="$major.$((minor + 1)).0"
  tbump "$next"
}

function tbump-major() {
  local current
  current=$(tbump current-version)
  local major
  major=$(echo "$current" | cut -d. -f1)
  local next
  next="$((major + 1)).0.0"
  tbump "$next"
}
