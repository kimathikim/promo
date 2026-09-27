-- promo.nvim: drive the PROmodoro timer without leaving Neovim.
--
--   require("promo").setup({ keymaps = true })
--   lualine: sections = { lualine_x = { require("promo").statusline } }

local M = {}
local uv = vim.uv or vim.loop

M.config = {
  cmd = "promo", -- the promo executable
  keymaps = false, -- set true for the <leader>p* mappings below
  icons = { focus = "🍅", ["break"] = "☕", long_break = "🌴", paused = "⏸" },
  window = { width = 0.8, height = 0.8, border = "rounded" },
}

local function cache_dir()
  local base = os.getenv("XDG_CACHE_HOME")
  if not base or base == "" then
    base = (os.getenv("HOME") or "") .. "/.cache"
  end
  return base .. "/promo"
end

--- State of the running timer, or nil when none is running.
function M.state()
  local f = io.open(cache_dir() .. "/state.json", "r")
  if not f then
    return nil
  end
  local ok, st = pcall(vim.json.decode, f:read("*a"))
  f:close()
  if not ok or type(st) ~= "table" or not st.pid then
    return nil
  end
  if not uv.kill(st.pid, 0) then -- stale file from a crashed timer
    return nil
  end
  return st
end

local function fmt_clock(seconds)
  seconds = math.max(0, math.ceil(seconds))
  local h, m, s = math.floor(seconds / 3600), math.floor(seconds % 3600 / 60), seconds % 60
  if h > 0 then
    return string.format("%d:%02d:%02d", h, m, s)
  end
  return string.format("%02d:%02d", m, s)
end

--- Statusline component: "🍅 18:33", or "" when no timer is running.
function M.statusline()
  local st = M.state()
  if not st then
    return ""
  end
  local remaining = st.remaining or 0
  if not st.paused and st.ends_at and st.ends_at ~= vim.NIL then
    remaining = st.ends_at - os.time()
  end
  local icon = st.paused and M.config.icons.paused or (M.config.icons[st.phase] or "")
  local text = icon .. " " .. fmt_clock(remaining)
  if (st.combo or 0) >= 2 then
    text = text .. " 🔥" .. st.combo
  end
  return text
end

local function run(args, on_ok)
  local cmd = { M.config.cmd }
  vim.list_extend(cmd, args)
  local err = {}
  local ok, job = pcall(vim.fn.jobstart, cmd, {
    stdout_buffered = true,
    stderr_buffered = true,
    on_stderr = function(_, data)
      err = data
    end,
    on_exit = function(_, code)
      vim.schedule(function()
        if code ~= 0 then
          local msg = vim.trim(table.concat(err or {}, "\n"))
          vim.notify(msg ~= "" and msg or ("promo exited with " .. code), vim.log.levels.WARN)
        elseif on_ok then
          on_ok()
        end
      end)
    end,
  })
  if not ok or job <= 0 then
    vim.notify("promo: could not run `" .. M.config.cmd .. "`", vim.log.levels.ERROR)
  end
end

-- Floating terminal holding the timer UI --------------------------------------
local term = { buf = nil, win = nil }

local function open_float()
  local w = math.floor(vim.o.columns * M.config.window.width)
  local h = math.floor(vim.o.lines * M.config.window.height)
  term.win = vim.api.nvim_open_win(term.buf, true, {
    relative = "editor",
    width = w,
    height = h,
    row = math.floor((vim.o.lines - h) / 2),
    col = math.floor((vim.o.columns - w) / 2),
    style = "minimal",
    border = M.config.window.border,
    title = " promo ",
    title_pos = "center",
  })
  vim.cmd.startinsert()
end

--- Show or hide the timer window, starting the timer if needed.
function M.open(args)
  if term.win and vim.api.nvim_win_is_valid(term.win) then
    vim.api.nvim_win_hide(term.win)
    term.win = nil
    return
  end
  if term.buf and vim.api.nvim_buf_is_valid(term.buf) then
    open_float()
    return
  end
  if M.state() then
    vim.notify("promo is already running elsewhere: " .. M.statusline())
    return
  end
  term.buf = vim.api.nvim_create_buf(false, true)
  vim.bo[term.buf].bufhidden = "hide"
  open_float()
  local cmd = { M.config.cmd }
  vim.list_extend(cmd, args or {})
  local opts = {
    on_exit = function()
      vim.schedule(function()
        if term.win and vim.api.nvim_win_is_valid(term.win) then
          vim.api.nvim_win_close(term.win, true)
        end
        term.win, term.buf = nil, nil
      end)
    end,
  }
  if vim.fn.has("nvim-0.11") == 1 then
    opts.term = true
    vim.fn.jobstart(cmd, opts)
  else
    vim.fn.termopen(cmd, opts)
  end
  -- <C-q> hides the window from terminal mode; the timer keeps running
  vim.keymap.set("t", "<C-q>", function()
    M.open()
  end, { buffer = term.buf, desc = "promo: hide timer" })
end

--- Save a note. Without text, captures `file:line` and the current line.
function M.note(text)
  if not text or text == "" then
    local file = vim.fn.expand("%:~:.")
    local line = vim.api.nvim_win_get_cursor(0)[1]
    local code = vim.trim(vim.api.nvim_get_current_line())
    text = string.format("`%s:%d` %s", file ~= "" and file or "[No Name]", line, code)
  end
  run({ "note", text }, function()
    vim.notify("promo: note saved")
  end)
end

local SUBCOMMANDS = { "open", "toggle", "pause", "resume", "skip", "stop", "add", "sub",
  "task", "rate", "note", "status" }

function M.command(opts)
  local args = opts.fargs
  local sub = table.remove(args, 1) or "open"
  if sub == "open" or sub == "start" then
    M.open(args)
  elseif sub == "note" then
    M.note(table.concat(args, " "))
  elseif sub == "status" then
    local s = M.statusline()
    vim.notify(s ~= "" and ("promo " .. s) or "promo: no timer running")
  elseif sub == "add" or sub == "sub" then
    run({ sub, args[1] or "5" })
  else
    run(vim.list_extend({ sub }, args))
  end
end

function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", M.config, opts or {})
  vim.api.nvim_create_user_command("Promo", M.command, {
    nargs = "*",
    desc = "PROmodoro timer",
    complete = function(lead, line)
      if #vim.split(line, "%s+") > 2 then
        return {}
      end
      return vim.tbl_filter(function(c)
        return c:find(lead, 1, true) == 1
      end, SUBCOMMANDS)
    end,
  })
  vim.api.nvim_create_user_command("PromoNote", function(o)
    M.note(o.args)
  end, { nargs = "*", desc = "promo: save a note (default: file:line)" })

  if M.config.keymaps then
    local map = function(lhs, rhs, desc)
      vim.keymap.set("n", lhs, rhs, { desc = "promo: " .. desc })
    end
    map("<leader>po", M.open, "open / hide timer")
    map("<leader>pp", function() run({ "toggle" }) end, "pause / resume")
    map("<leader>ps", function() run({ "skip" }) end, "skip phase")
    map("<leader>pn", function() M.note() end, "note file:line")
    map("<leader>pa", function() run({ "add", "5" }) end, "add 5 minutes")
  end

  -- keep statuslines ticking while a timer runs
  if not M._timer then
    M._timer = uv.new_timer()
    M._timer:start(1000, 1000, vim.schedule_wrap(function()
      if M.state() then
        vim.cmd.redrawstatus()
      end
    end))
  end
end

return M
