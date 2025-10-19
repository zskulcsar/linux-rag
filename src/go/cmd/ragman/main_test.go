package main

import (
	"strings"
	"testing"
	"time"
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
	if !strings.Contains(message, "Run 'ragman ask --help'") {
		t.Errorf("expected help guidance in error message, got: %s", message)
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
	if !strings.Contains(message, "Run 'ragman ask --help'") {
		t.Errorf("expected help guidance in format error, got: %s", message)
	}
}

func TestExecuteRejectsUnknownModel(t *testing.T) {
	message := requireExecuteError(t, []string{"ask", "--model", "gpt-4", "Give me SELinux troubleshooting steps"})

	if !strings.Contains(message, "--model") {
		t.Errorf("expected error to reference --model flag, got: %s", message)
	}
	if !strings.Contains(strings.ToLower(message), "allowed values") {
		t.Errorf("expected error to mention allowed values, got: %s", message)
	}
	if strings.Contains(message, "gpt-4") && !strings.Contains(message, "gemma3:1b") {
		t.Errorf("expected guidance to suggest supported models, got: %s", message)
	}
	if !strings.Contains(message, "Run 'ragman ask --help'") {
		t.Errorf("expected help guidance in model error, got: %s", message)
	}
}

func TestExecuteUnknownFlagProvidesGuidance(t *testing.T) {
	message := requireExecuteError(t, []string{"ask", "--unknown"})

	if !strings.Contains(strings.ToLower(message), "unknown flag") {
		t.Errorf("expected unknown flag message, got: %s", message)
	}
	if !strings.Contains(message, "Run 'ragman ask --help'") {
		t.Errorf("expected help guidance for unknown flag, got: %s", message)
	}
}

func TestResolveEndpointSupportsUnixPaths(t *testing.T) {
	opts := askOptions{
		socket:  "/tmp/rag-service.sock",
		timeout: time.Second,
	}

	target, dialOpts := resolveEndpoint(opts)

	if target != "unix:///tmp/rag-service.sock" {
		t.Fatalf("expected unix target, got %s", target)
	}
	if len(dialOpts) != 1 {
		t.Fatalf("expected context dialer to be configured for unix sockets")
	}
}

func TestResolveEndpointSupportsTCP(t *testing.T) {
	opts := askOptions{
		socket:  "tcp://127.0.0.1:50051",
		timeout: time.Second,
	}

	target, dialOpts := resolveEndpoint(opts)

	if target != "127.0.0.1:50051" {
		t.Fatalf("expected tcp target without scheme, got %s", target)
	}
	if len(dialOpts) != 0 {
		t.Fatalf("expected no custom dial options for tcp endpoints")
	}
}

func TestMockAnswerViewIncludesCitation(t *testing.T) {
	opts := askOptions{
		model: "gemma3:1b",
	}

	view := mockAnswerView("Check services", opts)

	if view.SessionID == "" {
		t.Fatalf("expected mock session id to be set")
	}
	if len(view.Citations) != 1 {
		t.Fatalf("expected single citation, got %d", len(view.Citations))
	}
	if !strings.HasPrefix(view.Citations[0].SourcePath, "/") {
		t.Fatalf("expected citation path to be absolute, got %s", view.Citations[0].SourcePath)
	}
}
