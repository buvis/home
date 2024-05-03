local autoload = require('buvis.autoload')

local buvis = autoload('buvis')

-- Using a real global here to make sure anything stashed in here (and
-- in `wincent.g`) survives even after the last reference to it goes away.
_G.buvis = buvis

require('buvis.core')
require('buvis.plugin.focus')

return buvis
