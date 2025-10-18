package main

import (
	"fmt"
	"strings"

	"github.com/spf13/cobra"
)

const helpTemplate = "Run '%s --help' for usage details."

// errorWithGuidance appends consistent help guidance to user-facing errors.
func errorWithGuidance(cmd *cobra.Command, message string) error {
	hint := fmt.Sprintf(helpTemplate, cmd.CommandPath())
	return fmt.Errorf("%s\n\n%s", strings.TrimSpace(message), hint)
}

// newFlagValueError reports an invalid flag value along with accepted options.
func newFlagValueError(cmd *cobra.Command, flagName, value string, allowed []string) error {
	formatted := fmt.Sprintf("--%s %q is not supported; allowed values: %s", flagName, value, strings.Join(allowed, ", "))
	return errorWithGuidance(cmd, formatted)
}

// newFlagParseError normalises Cobra flag parsing errors with extra guidance.
func newFlagParseError(cmd *cobra.Command, err error) error {
	if err == nil {
		return nil
	}
	return errorWithGuidance(cmd, err.Error())
}

// newMissingConfigError wraps missing config path scenarios with help text.
func newMissingConfigError(cmd *cobra.Command) error {
	return errorWithGuidance(cmd, "configuration file is required; provide --config <path>")
}

// newMissingSourceError highlights ingestion commands that omit source flags.
func newMissingSourceError(cmd *cobra.Command) error {
	return errorWithGuidance(cmd, "ingest requires --man-root or at least one --wiki archive")
}
