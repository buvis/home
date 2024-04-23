-- Provides a lazy autoload mechanism similar to Vimscript's autoload mechanism.
--
-- Examples:
--
--    " Vimscript - looks for function named `buvis#foo#bar#baz()` in
--    " autoload/buvis/foo/bar.vim):
--
--    call buvis#foo#bar#baz()
--
--    -- Lua - lazy-loads these files in sequence before calling
--    -- `buvis.foo.bar.baz()`:
--    --
--    --    1. lua/buvis/foo.lua (or lua/buvis/foo/init.lua)
--    --    2. lua/buvis/foo/bar.lua (or lua/buvis/foo/bar/init.lua)
--    --    3. lua/buvis/foo/bar/baz.lua (or lua/buvis/foo/bar/baz/init.lua)
--
--    local buvis = require('buvis')
--    buvis.foo.bar.baz()
--
--    -- Note that because `require('buvis')` appears at the top of the top-level
--    -- init.lua, the previous example can be written as:
--
--    buvis.foo.bar.baz()
--
local autoload = function(base)
  local storage = {}
  local mt = {
    __index = function(_, key)
      if storage[key] == nil then
        storage[key] = require(base .. '.' .. key)
      end
      return storage[key]
    end,
  }

  return setmetatable({}, mt)
end

return autoload
