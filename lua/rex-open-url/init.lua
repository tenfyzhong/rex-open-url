local M = {}
local options = {}
local source = debug.getinfo(1, 'S').source:gsub('^@', '')
local root = assert(source:match('^(.*)/lua/rex%-open%-url/init%.lua$'),
    'open-url: cannot locate plugin directory')

function M.setup(config)
    options = config or {}
end

local function rex_executable()
    if options.rex then return options.rex end
    local home = os.getenv('HOME')
    if home then
        local bundled = home .. '/Library/Application Support/com.superlogical.rex/'
            .. 'RexServer/Versions/Current/Rex Server.app/Contents/MacOS/rex'
        local file = io.open(bundled, 'r')
        if file then
            file:close()
            return bundled
        end
    end
    return 'rex'
end

local function encode_options()
    for _, key in ipairs({'open_command', 'copy_command'}) do
        local command = options[key]
        if command then
            assert(type(command) == 'table' and #command > 0,
                'open-url: ' .. key .. ' must be a nonempty argv list')
            for _, arg in ipairs(command) do
                assert(type(arg) == 'string', 'open-url: ' .. key .. ' must contain strings')
            end
        end
    end
    if options.history_limit then
        assert(type(options.history_limit) == 'number' and options.history_limit >= 1
            and options.history_limit % 1 == 0, 'open-url: history_limit must be a positive integer')
    end
    return assert(rex.json.encode({
        custom_pattern = options.custom_pattern, custom_sub = options.custom_sub,
        open_command = options.open_command, copy_command = options.copy_command,
        history_limit = options.history_limit,
    }))
end

local function run_helper(argv, stdin)
    local result, err = rex.exec(argv, {stdin = stdin})
    assert(result, err)
    if not result.ok then
        local message = (result.stderr or ''):gsub('%s+$', '')
        error(message ~= '' and message or 'open-url: helper failed', 0)
    end
    return result.stdout
end

local function prompt_result(value, reason, detail)
    if value == nil and reason ~= 'cancelled' then
        error('open-url: ' .. (detail or reason or 'Rex Custom UI failed'), 0)
    end
    return value
end

local function choose_url(urls, label)
    local all_urls = urls
    local query
    while #urls > 2000 do
        -- Rex limits each pick prompt to 2,000 items.
        query = prompt_result(rex.ui.input{
            title = 'Narrow ' .. #urls .. ' URLs to 2,000 or fewer',
            placeholder = 'Enter part of a URL', value = query,
        })
        if not query then return end
        local needle = query:lower()
        urls = {}
        for _, url in ipairs(all_urls) do
            if url:lower():find(needle, 1, true) then urls[#urls + 1] = url end
        end
    end
    return prompt_result(rex.ui.pick{
        title = #urls > 0 and label .. ' URLs' or 'No URLs found',
        placeholder = 'Filter URLs', items = urls, confirm = label,
    })
end

function M.open(ctx, copy)
    assert(ctx.session_id and ctx.block_id, 'open-url: no terminal pane context')
    assert(rex.ui and rex.ui.pick, 'open-url: Rex Custom UI is required')
    local dimensions, size_err = rex.block.call('com.superlogical.terminal', 'size', {
        session_id = ctx.session_id, block_id = ctx.block_id,
    })
    assert(dimensions, size_err)

    local python = options.python or 'python3'
    local helper = root .. '/picker.py'
    local settings = encode_options()
    local urls = assert(rex.json.decode(run_helper({
        python, helper, 'collect', '--rex', rex_executable(),
        '--session', ctx.session_id, '--pane', ctx.block_id,
        '--rows', tostring(dimensions.rows), '--columns', tostring(dimensions.columns),
        '--options', settings,
    })))
    local url = choose_url(urls, copy and 'Copy' or 'Open')
    if url then
        run_helper({python, helper, copy and 'copy' or 'open', '--options', settings}, url)
    end
    if ctx.client_id and ctx.origin == 'key' then rex.client.queue('client.mode.exit_all') end
end

rex.action{
    name = 'open_url', title = 'Open URL: Pick from Current Pane',
    description = 'Filter and open URLs from the terminal.',
    run = function(ctx) return M.open(ctx) end,
}
rex.action{
    name = 'open_url_copy', title = 'Open URL: Copy from Current Pane',
    description = 'Filter and copy URLs from the terminal.',
    run = function(ctx) return M.open(ctx, true) end,
}
rex.bind('prefix/u', 'open_url')
rex.bind('terminal_prefix/u', 'open_url')
return M
