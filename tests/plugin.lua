package.path = './lua/?.lua;./lua/?/init.lua;' .. package.path

local actions, bindings = {}, {}
local ctx = {session_id = 'session', block_id = 'source', client_id = 'client', origin = 'key'}
local urls = {'https://example.com/a', 'https://example.com/b'}
local config = {
    python = '/python', rex = '/rex', history_limit = 25,
    custom_pattern = 'BUG-%d+', custom_sub = 'https://tracker/',
    open_command = {'browser', '--new-window'}, copy_command = {'clipboard'},
}
local executions, prompts, filters, queued = {}, {}, {}, {}
local selection, reason, query, command_error

rex = {
    action = function(action) actions[action.name] = action end,
    bind = function(key, action) bindings[key] = action end,
    exec = function(argv, opts)
        executions[#executions + 1] = {argv = argv, opts = opts}
        if argv[3] == 'collect' then return {ok = true, stdout = 'urls'} end
        if command_error then return {ok = false, stderr = command_error} end
        return {ok = true, stdout = ''}
    end,
    json = {
        encode = function(value)
            assert(value.history_limit == 25)
            assert(value.custom_pattern == config.custom_pattern and value.custom_sub == config.custom_sub)
            assert(value.open_command == config.open_command and value.copy_command == config.copy_command)
            return 'config'
        end,
        decode = function(value)
            assert(value == 'urls')
            return urls
        end,
    },
    client = {queue = function(action) queued[#queued + 1] = action end},
    ui = {
        pick = function(prompt)
            assert(not prompt.multiple, 'Return must confirm one highlighted URL')
            prompts[#prompts + 1] = prompt
            return selection, reason
        end,
        input = function(prompt)
            filters[#filters + 1] = prompt
            return query
        end,
    },
    block = {call = function(creator, method, args)
        assert(creator == 'com.superlogical.terminal' and method == 'size')
        assert(args.session_id == 'session' and args.block_id == 'source')
        return {rows = 24, columns = 80}
    end},
}

local plugin = require('rex-open-url')
assert(bindings['prefix/u'] == 'open_url')
assert(bindings['terminal_prefix/u'] == 'open_url')
plugin.setup(config)

selection = urls[2]
actions.open_url.run(ctx)
assert(#prompts == 1 and prompts[1].confirm == 'Open')
assert(prompts[1].items[1] == urls[1] and prompts[1].items[2] == urls[2])
local argv = executions[1].argv
assert(argv[1] == '/python' and argv[2]:match('picker%.py$'))
assert(table.concat(argv, ' ', 3) ==
    'collect --rex /rex --session session --pane source --rows 24 --columns 80 --options config')
assert(executions[2].argv[3] == 'open' and executions[2].argv[5] == 'config')
assert(executions[2].opts.stdin == urls[2])
assert(queued[1] == 'client.mode.exit_all')

selection = urls[1]
actions.open_url_copy.run({
    session_id = ctx.session_id, block_id = ctx.block_id, client_id = ctx.client_id, origin = 'cli',
})
assert(prompts[2].confirm == 'Copy')
assert(executions[4].argv[3] == 'copy' and executions[4].opts.stdin == urls[1])
assert(#queued == 1, 'CLI actions must not queue a key-mode change')

selection, reason = nil, 'cancelled'
actions.open_url.run(ctx)
assert(#executions == 5, 'cancel must only collect links')

urls = {}
actions.open_url.run(ctx)
assert(#prompts[4].items == 0 and #executions == 6)

command_error = 'browser failed'
urls, selection = {'https://example.com/a'}, 'https://example.com/a'
local ok, err = pcall(actions.open_url.run, ctx)
assert(not ok and err:find(command_error, 1, true))

command_error = nil
for i = 2, 2001 do urls[i] = 'https://example.com/' .. i end
query, selection = '/2001', nil
actions.open_url.run(ctx)
assert(#filters == 1 and #prompts[6].items == 1 and prompts[6].items[1] == urls[2001])

local missing = pcall(actions.open_url.run, {})
assert(not missing, 'missing source context must fail')
