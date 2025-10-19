package main

import (
	"strings"
	"testing"
)

func requireExecuteError(t *testing.T, args []string) string {
	t.Helper()

	err := Execute(args)
	if err == nil {
		t.Fatalf("expected Execute(%v) to return an error", args)
	}
	return err.Error()
}

func TestRunCommandRequiresConfig(t *testing.T) {
	errMsg := requireExecuteError(t, []string{"run"})

	if !strings.Contains(errMsg, "--config") {
		t.Fatalf("expected run command to require --config, got: %s", errMsg)
	}
}

func TestIngestRequiresManRootOrWiki(t *testing.T) {
	errMsg := requireExecuteError(t, []string{"ingest", "--config", "configs/local.yaml"})

	if !strings.Contains(strings.ToLower(errMsg), "man-root") &&
		!strings.Contains(strings.ToLower(errMsg), "wiki") {
		t.Fatalf("expected ingest to reference required sources, got: %s", errMsg)
	}
}

func TestStatusSupportsJSONFormat(t *testing.T) {
	errMsg := requireExecuteError(t, []string{"status", "--config", "configs/local.yaml", "--format", "yaml"})

	if !strings.Contains(errMsg, "--format") {
		t.Fatalf("expected status format validation, got: %s", errMsg)
	}
	if !strings.Contains(errMsg, "json") {
		t.Fatalf("expected status validation to mention json format, got: %s", errMsg)
	}
}
