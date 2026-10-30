local M = {}
local options = {}
local source = debug.getinfo(1, 'S').source:gsub('^@', '')
local root = assert(source:match('^(.*)/lua/rex%-open%-url/init%.lua$'),
    'open-url: cannot locate plugin directory')

function M.setup(config)
    options = config or {}
end

local function contains(node, id)
    if not node then return false end
    if node.block_id == id then return true end
    return node.split and (contains(node.split.before, id) or contains(node.split.after, id))
end

function M.open(ctx)
    assert(ctx.session_id and ctx.block_id, 'open-url: no terminal pane context')
    local view, err = rex.session.view{session_id = ctx.session_id}
    assert(view, err)
    local window_id
    for _, window in ipairs(view.windows or {}) do
        for _, layer in ipairs(window.layers or {}) do
            if contains(layer.layout, ctx.block_id) then window_id = window.window_id end
        end
    end
    assert(window_id, 'open-url: source pane is not placed')
    local dimensions, size_err = rex.block.call('com.superlogical.terminal', 'size', {
        session_id = ctx.session_id, block_id = ctx.block_id,
    })
    assert(dimensions, size_err)
    local python = options.python or 'python3'
    local ready, check_err = rex.exec({python, '-c', 'import curses'})
    assert(ready and ready.ok, check_err or 'open-url: Python 3 with curses is required')
    local rex_path = options.rex or 'rex'
    if not options.rex then
        local bundled = os.getenv('HOME') .. '/Library/Application Support/com.superlogical.rex/'
            .. 'RexServer/Versions/Current/Rex Server.app/Contents/MacOS/rex'
        local file = io.open(bundled, 'r')
        if file then file:close(); rex_path = bundled end
    end
    local command = {python, root .. '/picker.py', '--rex', rex_path,
        '--session', ctx.session_id, '--pane', ctx.block_id,
        '--rows', tostring(dimensions.rows), '--columns', tostring(dimensions.columns)}
    -- Encode the small options table without requiring a JSON package.
    local function quote(value)
        return '"' .. value:gsub('[%z\1-\31\\"]', function(char)
            return string.format('\\u%04x', string.byte(char))
        end) .. '"'
    end
    local fields = {}
    for _, key in ipairs({'custom_pattern', 'custom_sub'}) do
        if options[key] then fields[#fields + 1] = quote(key) .. ':' .. quote(options[key]) end
    end
    for _, key in ipairs({'open_command', 'copy_command'}) do
        if options[key] then
            assert(type(options[key]) == 'table' and #options[key] > 0,
                'open-url: ' .. key .. ' must be a nonempty argv list')
            local values = {}
            for _, value in ipairs(options[key]) do values[#values + 1] = quote(value) end
            fields[#fields + 1] = quote(key) .. ':[' .. table.concat(values, ',') .. ']'
        end
    end
    if options.history_limit then
        assert(type(options.history_limit) == 'number' and options.history_limit >= 1
            and options.history_limit % 1 == 0, 'open-url: history_limit must be a positive integer')
        fields[#fields + 1] = '"history_limit":' .. tostring(options.history_limit)
    end
    command[#command + 1] = '--options'
    command[#command + 1] = '{' .. table.concat(fields, ',') .. '}'
    local result, layer_err = rex.session.new_layer{
        session_id = ctx.session_id, window_id = window_id,
        bounds = {0, 0, 1, 1}, focus = true,
        layout = {block = {
            flavor = 'com.superlogical.terminal.shell', label = 'Open URL',
            options = {shell = 'none', command = command, exit = {on_completion = true}},
        }},
    }
    assert(result, layer_err)
    if ctx.client_id then rex.client.queue('client.mode.exit_all') end
    return result
end

rex.action{
    name = 'open_url', title = 'Open URL: Pick from Current Pane',
    description = 'Filter, select, open or copy URLs from the terminal.',
    run = function(ctx) return M.open(ctx) end,
}
rex.bind('prefix/u', 'open_url')
rex.bind('terminal_prefix/u', 'open_url')
return M
