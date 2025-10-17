package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"strings"
	"time"

	contractspb "github.com/linux-rag/linux-rag/internal/contracts"
	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const (
	defaultSocketPath = "/run/linux-rag/rag-service.sock"
	defaultTimeout    = 15 * time.Second
)

var (
	allowedFormats = []string{string(FormatText), string(FormatJSON)}
	allowedModels  = []string{"gemma3:1b", "codegemma:2b"}
)

type askOptions struct {
	hints      []string
	model      string
	format     string
	allowCache bool
	socket     string
	timeout    time.Duration
}

func main() {
	if err := Execute(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// Execute exposes command execution for tests.
func Execute(args []string) error {
	cmd := newRootCmd()
	cmd.SetArgs(args)
	return cmd.Execute()
}

func newRootCmd() *cobra.Command {
	root := cobra.NewCommand("ragman")
	root.Short = "Linux RAG assistant CLI"
	root.SilenceUsage = true
	root.SilenceErrors = true

	root.AddCommand(newAskCmd())
	return root
}

func newAskCmd() *cobra.Command {
	opts := askOptions{
		model:      allowedModels[0],
		format:     string(FormatText),
		allowCache: true,
		socket:     defaultSocketPath,
		timeout:    defaultTimeout,
	}

	var noCache bool

	cmd := cobra.NewCommand("ask")
	cmd.Short = "Ask a question using the knowledge assistant"
	cmd.SilenceUsage = true
	cmd.SilenceErrors = true

	flags := cmd.Flags()
	flags.StringVarP(&opts.model, "model", "m", opts.model, "Model to use")
	flags.StringVarP(&opts.format, "format", "f", opts.format, "Output format (text or json)")
	flags.BoolVar(&noCache, "no-cache", false, "Bypass the response cache")
	flags.StringSliceVar(&opts.hints, "hint", nil, "Provide additional retrieval hints (repeatable)")
	flags.StringVar(&opts.socket, "socket", opts.socket, "Override the gRPC Unix socket path")
	flags.DurationVar(&opts.timeout, "timeout", opts.timeout, "Override RPC timeout (default 15s)")

	cmd.RunE = func(cmd *cobra.Command, args []string) error {
		opts.allowCache = !noCache
		opts.model = strings.TrimSpace(opts.model)
		opts.format = strings.ToLower(strings.TrimSpace(opts.format))
		opts.socket = strings.TrimSpace(opts.socket)

		if strings.TrimSpace(opts.socket) == "" {
			return fmt.Errorf("socket path must not be empty")
		}

		if !contains(allowedFormats, opts.format) {
			return fmt.Errorf("--format %q is not supported; allowed formats: %s", opts.format, strings.Join(allowedFormats, ", "))
		}
		if !contains(allowedModels, opts.model) {
			return fmt.Errorf("--model %q is not supported; available models: %s", opts.model, strings.Join(allowedModels, ", "))
		}

		question := strings.TrimSpace(strings.Join(args, " "))
		if question == "" {
			return fmt.Errorf("question text is required; run ragman ask \"How do I enable automount on boot?\"")
		}

		opts.hints = filterEmpty(opts.hints)
		return runAsk(question, opts)
	}

	return cmd
}

func runAsk(question string, opts askOptions) error {
	ctx, cancel := context.WithTimeout(context.Background(), opts.timeout)
	defer cancel()

	dialer := func(ctx context.Context, _ string) (net.Conn, error) {
		return net.DialTimeout("unix", opts.socket, opts.timeout)
	}

	conn, err := grpc.DialContext(
		ctx,
		"unix://"+opts.socket,
		grpc.WithContextDialer(dialer),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return fmt.Errorf("failed to connect to service at %s: %w", opts.socket, err)
	}
	defer conn.Close()

	client := contractspb.NewRagServiceClient(conn)
	request := &contractspb.AskRequest{
		QueryText:      question,
		ContextHints:   opts.hints,
		PreferredModel: opts.model,
		AllowCache:     opts.allowCache,
	}

	response, err := client.Ask(ctx, request)
	if err != nil {
		return fmt.Errorf("Ask RPC failed: %w", err)
	}

	view := AnswerView{
		Query:          question,
		SessionID:      response.GetSessionId(),
		Answer:         response.GetAnswerText(),
		Model:          opts.model,
		ResponseTimeMS: int(response.GetResponseTimeMs()),
		CacheHit:       response.GetCacheHit(),
		Citations:      make([]CitationView, 0, len(response.GetCitations())),
	}
	for _, citation := range response.GetCitations() {
		view.Citations = append(view.Citations, CitationView{
			SourceID:   citation.GetSourceId(),
			Title:      citation.GetTitle(),
			Snippet:    citation.GetSnippet(),
			SourcePath: citation.GetSourcePath(),
		})
	}

	rendered, renderErr := RenderAnswer(view, OutputFormat(opts.format))
	if renderErr != nil {
		rendered = fallbackRender(view, OutputFormat(opts.format))
	}

	fmt.Println(rendered)
	return nil
}

func fallbackRender(view AnswerView, format OutputFormat) string {
	switch format {
	case FormatJSON:
		payload := map[string]any{
			"query":            view.Query,
			"session_id":       view.SessionID,
			"answer":           view.Answer,
			"model":            view.Model,
			"response_time_ms": view.ResponseTimeMS,
			"cache_hit":        view.CacheHit,
			"citations":        view.Citations,
		}
		bytes, err := json.MarshalIndent(payload, "", "  ")
		if err != nil {
			return view.Answer
		}
		return string(bytes)
	default:
		var b strings.Builder
		b.WriteString(view.Answer)
		if len(view.Citations) > 0 {
			b.WriteString("\n\nSources:\n")
			for i, citation := range view.Citations {
				fmt.Fprintf(&b, "[%d] %s\n    %s\n", i+1, citation.Title, citation.SourcePath)
				snippet := strings.TrimSpace(citation.Snippet)
				if snippet != "" {
					fmt.Fprintf(&b, "    %s\n", snippet)
				}
			}
		}
		return b.String()
	}
}

func filterEmpty(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	filtered := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			filtered = append(filtered, value)
		}
	}
	return filtered
}

func contains(values []string, candidate string) bool {
	for _, value := range values {
		if strings.EqualFold(value, candidate) {
			return true
		}
	}
	return false
}
