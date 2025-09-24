return {
  {
    "mason-org/mason.nvim",
    config = function(_, opts)
      if vim.fn.has("win32") == 1 then
        -- Create a temporary PowerShell profile for Mason
        local profile_content = "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}"
        local temp_profile = vim.fn.tempname() .. ".ps1"
        vim.fn.writefile({ profile_content }, temp_profile)

        -- Override Mason's PowerShell to use the profile
        local spawn = require("mason-core.spawn")
        local original_pwsh = spawn.pwsh

        spawn.pwsh = function(args)
          local new_args = { "-ExecutionPolicy", "Bypass", "-File", temp_profile, ";" }
          vim.list_extend(new_args, args)
          return original_pwsh(new_args)
        end
      end

      require("mason").setup(opts)
    end,
    opts = function(_, opts)
      opts.ensure_installed = opts.ensure_installed or {}
      table.insert(opts.ensure_installed, "harper-ls")
      return opts
    end,
  },
}
