package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

const helpTemplate = "Run '%s --help' for usage details."

// errorWithGuidance appends a standard help hint to user-facing errors.
func errorWithGuidance(cmd *cobra.Command, message string) error {
	hint := fmt.Sprintf(helpTemplate, cmd.CommandPath())
	return fmt.Errorf("%s\n\n%s", message, hint)
}

// newFlagValueError returns an error for invalid flag values and lists allowed options.
func newFlagValueError(cmd *cobra.Command, flagName, value string, allowed []string) error {
	formatted := fmt.Sprintf("--%s %q is not supported; allowed values: %s", flagName, value, strings.Join(allowed, ", "))
	return errorWithGuidance(cmd, formatted)
}

// newRequiredArgumentError indicates a missing positional argument with guidance.
func newRequiredArgumentError(cmd *cobra.Command, message string) error {
	return errorWithGuidance(cmd, message)
}

// newFlagParseError wraps Cobra flag parsing errors with consistent guidance.
func newFlagParseError(cmd *cobra.Command, err error) error {
	if err == nil {
		return nil
	}
	return errorWithGuidance(cmd, strings.TrimSpace(err.Error()))
}
