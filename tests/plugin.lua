package.path = './lua/?.lua;./lua/?/init.lua;' .. package.path
local actions, bindings, request = {}, {}, nil
rex = {
    action = function(action) actions[action.name] = action end,
    bind = function(key, action) bindings[key] = action end,
    exec = function() return {ok = true} end,
    client = {queue = function() end},
    session = {
        view = function() return {windows = {{window_id = 'target', layers = {
            {layout = {block_id = 'source'}}
        }}}} end,
        new_layer = function(args) request = args; return {block_ids = {'picker'}} end,
    },
    block = {call = function(_, method)
        assert(method == 'size')
        return {rows = 24, columns = 80}
    end},
}
local plugin = require('rex-open-url')
assert(bindings['prefix/u'] == 'open_url')
assert(bindings['terminal_prefix/u'] == 'open_url')
plugin.setup({python = '/python', rex = '/rex'})
actions.open_url.run({session_id = 'session', block_id = 'source'})
assert(request.window_id == 'target')
assert(request.session_id == 'session')
assert(request.layout.block.options.command[1] == '/python')
assert(request.layout.block.options.exit.on_completion)
assert(not request.layout.split)
local ok = pcall(actions.open_url.run, {})
assert(not ok, 'missing source context must fail')
