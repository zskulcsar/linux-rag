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

func TestExecuteRequiresQuestionArgument(t *testing.T) {
	message := requireExecuteError(t, []string{"ask"})

	if !strings.Contains(strings.ToLower(message), "question") {
		t.Errorf("expected error to mention missing question, got: %s", message)
	}
	if !strings.Contains(message, `ragman ask "How do I enable automount on boot?"`) {
		t.Errorf("expected example usage in error message, got: %s", message)
	}
}

func TestExecuteRejectsUnsupportedFormat(t *testing.T) {
	message := requireExecuteError(t, []string{"ask", "--format", "yaml", "Show mounted volumes"})

	if !strings.Contains(message, "--format") {
		t.Errorf("expected error to reference --format flag, got: %s", message)
	}
	for _, allowed := range []string{"text", "json"} {
		if !strings.Contains(message, allowed) {
			t.Errorf("expected error to list allowed formats %q, message: %s", allowed, message)
			break
		}
	}
}

func TestExecuteRejectsUnknownModel(t *testing.T) {
	message := requireExecuteError(t, []string{"ask", "--model", "gpt-4", "Give me SELinux troubleshooting steps"})

	if !strings.Contains(message, "--model") {
		t.Errorf("expected error to reference --model flag, got: %s", message)
	}
	if !strings.Contains(strings.ToLower(message), "available models") {
		t.Errorf("expected error to mention available models, got: %s", message)
	}
	if strings.Contains(message, "gpt-4") && !strings.Contains(message, "gemma3:1b") {
		t.Errorf("expected guidance to suggest supported models, got: %s", message)
	}
}
