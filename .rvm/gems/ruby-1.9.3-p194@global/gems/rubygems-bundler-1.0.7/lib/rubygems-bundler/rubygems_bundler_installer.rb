module RubyGemsBundlerInstaller
  # Iterate through executables and generate wrapper for each one,
  # extract of rubygems code
  def self.bundler_generate_bin(inst)
    return if inst.spec.executables.nil? or inst.spec.executables.empty?
    bindir = inst.bin_dir ? inst.bin_dir : Gem.bindir(inst.gem_home)
    inst.spec.executables.each do |filename|
      filename.untaint
      original = File.join bindir, filename
      if File.exists?( original )
        bin_script_path = File.join bindir, inst.formatted_program_filename(filename)
        FileUtils.rm_f bin_script_path
        File.open bin_script_path, 'wb', 0755 do |file|
          file.print bundler_app_script_text(inst, filename)
        end
        inst.say bin_script_path if Gem.configuration.really_verbose
      else
        inst.say "Can not find #{inst.spec.name} in GEM_PATH"
        break
      end
    end
  end


  def self.shebang(inst, bin_file_name)
    # options were defined first in 1.5, we want to support back to 1.3.7
    ruby_name = Gem::ConfigMap[:ruby_install_name] if inst.instance_variable_get(:@env_shebang)
    bindir = inst.bin_dir ? inst.bin_dir : Gem.bindir(inst.gem_home)
    path = File.join bindir, inst.formatted_program_filename(bin_file_name)
    first_line = File.open(path, "rb") {|file| file.gets}

    if /\A#!/ =~ first_line then
      # Preserve extra words on shebang line, like "-w". Thanks RPA.
      shebang = first_line.sub(/\A\#!.*?ruby\S*((\s+\S+)+)/, "#!#{Gem.ruby}")
      opts = $1
      shebang.strip! # Avoid nasty ^M issues.
    end

    if which = Gem.configuration[:custom_shebang]
      which = which.gsub(/\$(\w+)/) do
        case $1
        when "env"
          @env_path ||= Gem::Installer::ENV_PATHS.find {|env_path| File.executable? env_path }
        when "ruby"
          "#{Gem.ruby}#{opts}"
        when "exec"
          bin_file_name
        when "name"
          inst.spec.name
        end
      end

      return "#!#{which}"
    end

    if not ruby_name then
      "#!#{Gem.ruby}#{opts}"
    elsif opts then
      "#!/bin/sh\n'exec' #{ruby_name.dump} '-x' \"$0\" \"$@\"\n#{shebang}"
    else
      @env_path ||= Gem::Installer::ENV_PATHS.find {|env_path| File.executable? env_path }
      "#!#{@env_path} #{ruby_name}"
    end
  end

  # Return the text for an application file.
  def self.bundler_app_script_text(inst, bin_file_name)
    <<-TEXT
#{shebang inst, bin_file_name}
#
# This file was generated by RubyGems.
#
# The application '#{inst.spec.name}' is installed as part of a gem, and
# this file is here to facilitate running it.
#

require 'rubygems'

version = "#{Gem::Requirement.default}"

if ARGV.first =~ /^_(.*)_$/ and Gem::Version.correct? $1 then
  version = $1
  ARGV.shift
end

gem '#{inst.spec.name}', version
load Gem.bin_path('#{inst.spec.name}', '#{bin_file_name}', version)
TEXT
  end

end

Gem.post_install do |inst|
  RubyGemsBundlerInstaller.bundler_generate_bin(inst)
end
