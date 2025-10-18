package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	contractspb "github.com/linux-rag/linux-rag/internal/contracts"
	"github.com/spf13/cobra"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const (
	defaultSocketPath   = "/run/linux-rag/rag-service.sock"
	defaultComposeFile  = "infra/podman-compose.yml"
	defaultProjectName  = "linux-rag"
	defaultWaitTimeout  = 120 * time.Second
	defaultRPCDeadline  = 30 * time.Second
	defaultPodmanBinary = "podman-compose"
)

var (
	allowedStatusFormats = []string{string(FormatText), string(FormatJSON)}
)

// OutputFormat enumerates supported status renderings.
type OutputFormat string

const (
	// FormatText renders human-readable text.
	FormatText OutputFormat = "text"
	// FormatJSON renders JSON payloads.
	FormatJSON OutputFormat = "json"
)

// StatusView captures status fields for presentation.
type StatusView struct {
	LatestJobID        string
	LatestJobStatus    string
	CacheDiskPercent   float64
	CacheHitRate       int
	ActiveModels       []string
	NextRunAt          string
	LastSuccessAt      string
	ManPagesProcessed  int
	WikiArticlesLoaded int
	Errors             []string
}

// RenderStatus formats status output in the requested format.
func RenderStatus(view StatusView, format OutputFormat) (string, error) {
	switch format {
	case FormatText:
		var b strings.Builder
		fmt.Fprintf(&b, "Latest ingestion job: %s (%s)\n", view.LatestJobID, view.LatestJobStatus)
		fmt.Fprintf(&b, "Cache usage: %.1f%%\n", view.CacheDiskPercent)
		fmt.Fprintf(&b, "Cache hit rate: %d%%\n", view.CacheHitRate)
		models := strings.Join(view.ActiveModels, ", ")
		if models == "" {
			models = "none"
		}
		fmt.Fprintf(&b, "Active models: %s\n", models)
		b.WriteString("\n")
		if view.NextRunAt != "" {
			fmt.Fprintf(&b, "Next scheduled run: %s\n", view.NextRunAt)
		} else {
			b.WriteString("Next scheduled run: unknown\n")
		}
		if view.LastSuccessAt != "" {
			fmt.Fprintf(&b, "Last successful run: %s\n", view.LastSuccessAt)
		} else {
			b.WriteString("Last successful run: unknown\n")
		}
		b.WriteString("\n")
		fmt.Fprintf(&b, "Man pages processed: %d\n", view.ManPagesProcessed)
		fmt.Fprintf(&b, "Wiki articles loaded: %d\n", view.WikiArticlesLoaded)
		if len(view.Errors) > 0 {
			b.WriteString("\nErrors:\n")
			for _, item := range view.Errors {
				fmt.Fprintf(&b, "- %s\n", item)
			}
		} else {
			b.WriteString("\n")
		}
		return b.String(), nil
	case FormatJSON:
		payload := struct {
			LatestJobID        string   `json:"latest_job_id"`
			LatestJobStatus    string   `json:"latest_job_status"`
			CacheDiskPercent   float64  `json:"cache_disk_pct"`
			CacheHitRate       int      `json:"cache_hit_rate"`
			ActiveModels       []string `json:"active_models"`
			NextRunAt          string   `json:"next_run_at"`
			LastSuccessAt      string   `json:"last_success_at"`
			ManPagesProcessed  int      `json:"man_pages_processed"`
			WikiArticlesLoaded int      `json:"wiki_articles_loaded"`
			Errors             []string `json:"errors"`
		}{
			LatestJobID:        view.LatestJobID,
			LatestJobStatus:    view.LatestJobStatus,
			CacheDiskPercent:   view.CacheDiskPercent,
			CacheHitRate:       view.CacheHitRate,
			ActiveModels:       view.ActiveModels,
			NextRunAt:          view.NextRunAt,
			LastSuccessAt:      view.LastSuccessAt,
			ManPagesProcessed:  view.ManPagesProcessed,
			WikiArticlesLoaded: view.WikiArticlesLoaded,
			Errors:             view.Errors,
		}
		bytes, err := json.MarshalIndent(payload, "", "  ")
		if err != nil {
			return "", err
		}
		return string(bytes) + "\n", nil
	default:
		return "", fmt.Errorf("unsupported format: %s", format)
	}
}

type rootOptions struct {
	configPath string
}

type runOptions struct {
	waitReady bool
}

type ingestOptions struct {
	manRoot       string
	wikiArchives  []string
	refreshManual bool
}

type statusOptions struct {
	format string
}

type adminConfig struct {
	Runtime   runtimeConfig   `yaml:"runtime"`
	Stack     stackConfig     `yaml:"stack"`
	Paths     pathsConfig     `yaml:"paths"`
	Ingestion ingestionConfig `yaml:"ingestion"`
}

type runtimeConfig struct {
	SocketPath string `yaml:"socket_path"`
	LogLevel   string `yaml:"log_level"`
}

type stackConfig struct {
	ComposeFile        string            `yaml:"compose_file"`
	ProjectName        string            `yaml:"project_name"`
	WaitTimeoutSeconds float64           `yaml:"wait_timeout_seconds"`
	Binary             string            `yaml:"binary"`
	Environment        map[string]string `yaml:"environment"`
}

type pathsConfig struct {
	DataRoot         string `yaml:"data_root"`
	CacheDir         string `yaml:"cache_dir"`
	WeaviateDataDir  string `yaml:"weaviate_data_dir"`
	OllamaModelsDir  string `yaml:"ollama_models_dir"`
	KiwixArchivesDir string `yaml:"kiwix_archives_dir"`
	LogsDir          string `yaml:"logs_dir"`
}

type ingestionConfig struct {
	ManpageRoot         string   `yaml:"manpage_root"`
	WikiExtractDir      string   `yaml:"wiki_extract_dir"`
	DefaultWikiArchives []string `yaml:"default_wiki_archives"`
}

func defaultAdminConfig() adminConfig {
	return adminConfig{
		Runtime: runtimeConfig{
			SocketPath: defaultSocketPath,
			LogLevel:   "info",
		},
		Stack: stackConfig{
			ComposeFile:        defaultComposeFile,
			ProjectName:        defaultProjectName,
			WaitTimeoutSeconds: defaultWaitTimeout.Seconds(),
			Binary:             defaultPodmanBinary,
			Environment:        map[string]string{},
		},
		Paths: pathsConfig{
			DataRoot:         "/var/lib/linux-rag",
			CacheDir:         "/var/lib/linux-rag/cache",
			WeaviateDataDir:  "/var/lib/linux-rag/weaviate",
			OllamaModelsDir:  "/var/lib/linux-rag/ollama",
			KiwixArchivesDir: "/var/lib/linux-rag/kiwix",
			LogsDir:          "/var/lib/linux-rag/logs",
		},
		Ingestion: ingestionConfig{
			ManpageRoot:         "/usr/share/man",
			WikiExtractDir:      "/var/lib/linux-rag/kiwix/extracted",
			DefaultWikiArchives: []string{},
		},
	}
}

func (c *adminConfig) applyDefaults(baseDir string) {
	if c.Runtime.SocketPath == "" {
		c.Runtime.SocketPath = defaultSocketPath
	}
	c.Runtime.SocketPath = resolvePath(c.Runtime.SocketPath, baseDir)

	if c.Stack.ComposeFile == "" {
		c.Stack.ComposeFile = defaultComposeFile
	}
	c.Stack.ComposeFile = resolvePath(c.Stack.ComposeFile, baseDir)
	if c.Stack.ProjectName == "" {
		c.Stack.ProjectName = defaultProjectName
	}
	if c.Stack.Binary == "" {
		c.Stack.Binary = defaultPodmanBinary
	}
	if c.Stack.WaitTimeoutSeconds <= 0 {
		c.Stack.WaitTimeoutSeconds = defaultWaitTimeout.Seconds()
	}

	c.Paths.DataRoot = defaultIfEmptyPath(c.Paths.DataRoot, "/var/lib/linux-rag", baseDir)
	c.Paths.CacheDir = defaultIfEmptyPath(c.Paths.CacheDir, filepath.Join(c.Paths.DataRoot, "cache"), baseDir)
	c.Paths.WeaviateDataDir = defaultIfEmptyPath(c.Paths.WeaviateDataDir, filepath.Join(c.Paths.DataRoot, "weaviate"), baseDir)
	c.Paths.OllamaModelsDir = defaultIfEmptyPath(c.Paths.OllamaModelsDir, filepath.Join(c.Paths.DataRoot, "ollama"), baseDir)
	c.Paths.KiwixArchivesDir = defaultIfEmptyPath(c.Paths.KiwixArchivesDir, filepath.Join(c.Paths.DataRoot, "kiwix"), baseDir)
	c.Paths.LogsDir = defaultIfEmptyPath(c.Paths.LogsDir, filepath.Join(c.Paths.DataRoot, "logs"), baseDir)

	if c.Ingestion.ManpageRoot == "" {
		c.Ingestion.ManpageRoot = "/usr/share/man"
	}
	c.Ingestion.ManpageRoot = resolvePath(c.Ingestion.ManpageRoot, baseDir)
	if c.Ingestion.WikiExtractDir == "" {
		c.Ingestion.WikiExtractDir = filepath.Join(c.Paths.KiwixArchivesDir, "extracted")
	}
	c.Ingestion.WikiExtractDir = resolvePath(c.Ingestion.WikiExtractDir, baseDir)

	if c.Ingestion.DefaultWikiArchives == nil {
		c.Ingestion.DefaultWikiArchives = []string{}
	}
}

func resolvePath(value, baseDir string) string {
	if value == "" {
		return value
	}
	expanded := os.ExpandEnv(value)
	if filepath.IsAbs(expanded) {
		return filepath.Clean(expanded)
	}
	if baseDir == "" {
		return filepath.Clean(expanded)
	}
	return filepath.Clean(filepath.Join(baseDir, expanded))
}

func defaultIfEmptyPath(current, fallback, baseDir string) string {
	if current == "" {
		current = fallback
	}
	return resolvePath(current, baseDir)
}

func loadConfig(path string) (adminConfig, error) {
	cfg := defaultAdminConfig()
	if err := parseConfigFile(path, &cfg); err != nil {
		return cfg, err
	}
	cfg.applyDefaults(filepath.Dir(path))
	return cfg, nil
}

func parseConfigFile(path string, cfg *adminConfig) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	section := ""
	subsection := ""
	currentList := ""

	for scanner.Scan() {
		line := scanner.Text()
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}

		indent := len(line) - len(strings.TrimLeft(line, " "))

		if strings.HasSuffix(trimmed, ":") {
			key := strings.TrimSuffix(trimmed, ":")
			switch indent {
			case 0:
				section = key
				subsection = ""
				currentList = ""
			case 2:
				subsection = key
				currentList = ""
				if section == "ingestion" && key == "default_wiki_archives" {
					currentList = key
					cfg.Ingestion.DefaultWikiArchives = cfg.Ingestion.DefaultWikiArchives[:0]
				}
			default:
				if section == "services" && key == "ollama" {
					subsection = "services.ollama"
				} else if section == "stack" && key == "environment" {
					subsection = "environment"
					cfg.Stack.Environment = make(map[string]string)
				}
			}
			continue
		}

		if strings.HasPrefix(trimmed, "- ") {
			if section == "ingestion" && currentList == "default_wiki_archives" {
				cfg.Ingestion.DefaultWikiArchives = append(cfg.Ingestion.DefaultWikiArchives, strings.TrimSpace(trimmed[2:]))
			}
			continue
		}

		parts := strings.SplitN(trimmed, ":", 2)
		if len(parts) != 2 {
			continue
		}

		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])
		value = strings.Trim(value, "\"'")

		switch section {
		case "runtime":
			switch key {
			case "socket_path":
				if value != "" {
					cfg.Runtime.SocketPath = value
				}
			case "log_level":
				if value != "" {
					cfg.Runtime.LogLevel = strings.ToLower(value)
				}
			}
		case "stack":
			if subsection == "environment" {
				if cfg.Stack.Environment == nil {
					cfg.Stack.Environment = make(map[string]string)
				}
				cfg.Stack.Environment[key] = value
				continue
			}
			switch key {
			case "compose_file":
				if value != "" {
					cfg.Stack.ComposeFile = value
				}
			case "project_name":
				if value != "" {
					cfg.Stack.ProjectName = value
				}
			case "wait_timeout_seconds":
				if parsed, err := strconv.ParseFloat(value, 64); err == nil {
					cfg.Stack.WaitTimeoutSeconds = parsed
				}
			case "binary":
				if value != "" {
					cfg.Stack.Binary = value
				}
			}
		case "paths":
			switch key {
			case "data_root":
				if value != "" {
					cfg.Paths.DataRoot = value
				}
			case "cache_dir":
				if value != "" {
					cfg.Paths.CacheDir = value
				}
			case "weaviate_data_dir":
				if value != "" {
					cfg.Paths.WeaviateDataDir = value
				}
			case "ollama_models_dir":
				if value != "" {
					cfg.Paths.OllamaModelsDir = value
				}
			case "kiwix_archives_dir":
				if value != "" {
					cfg.Paths.KiwixArchivesDir = value
				}
			case "logs_dir":
				if value != "" {
					cfg.Paths.LogsDir = value
				}
			}
		case "ingestion":
			switch key {
			case "manpage_root":
				if value != "" {
					cfg.Ingestion.ManpageRoot = value
				}
			case "wiki_extract_dir":
				if value != "" {
					cfg.Ingestion.WikiExtractDir = value
				}
			}
		}
	}

	return scanner.Err()
}

const helpTemplate = "Run '%s --help' for usage details."

func errorWithGuidance(cmd *cobra.Command, message string) error {
	hint := fmt.Sprintf(helpTemplate, cmd.CommandPath())
	return fmt.Errorf("%s\n\n%s", message, hint)
}

func newFlagValueError(cmd *cobra.Command, flagName, value string, allowed []string) error {
	formatted := fmt.Sprintf("--%s %q is not supported; allowed values: %s", flagName, value, strings.Join(allowed, ", "))
	return errorWithGuidance(cmd, formatted)
}

func newFlagParseError(cmd *cobra.Command, err error) error {
	if err == nil {
		return nil
	}
	return errorWithGuidance(cmd, strings.TrimSpace(err.Error()))
}

func (o *rootOptions) requireConfig(cmd *cobra.Command) (string, error) {
	path := strings.TrimSpace(o.configPath)
	if path == "" {
		return "", errorWithGuidance(cmd, "configuration file is required; provide --config <path>")
	}
	resolved, err := findConfigPath(path)
	if err != nil {
		return "", errorWithGuidance(cmd, fmt.Sprintf("unable to resolve config path: %v", err))
	}
	return resolved, nil
}

func findConfigPath(path string) (string, error) {
	if filepath.IsAbs(path) {
		return filepath.Clean(path), nil
	}

	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}

	dir := cwd
	for {
		candidate := filepath.Join(dir, path)
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	return filepath.Abs(path)
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
	opts := &rootOptions{}
	root := &cobra.Command{
		Use:           "ragman-admin",
		Short:         "Administer the Linux RAG stack",
		SilenceUsage:  true,
		SilenceErrors: true,
	}

	root.PersistentFlags().StringVar(&opts.configPath, "config", "", "Path to the runtime configuration file")

	root.AddCommand(newRunCmd(opts))
	root.AddCommand(newIngestCmd(opts))
	root.AddCommand(newStatusCmd(opts))
	return root
}

func newRunCmd(rootOpts *rootOptions) *cobra.Command {
	opts := runOptions{}
	cmd := &cobra.Command{
		Use:           "run",
		Short:         "Launch the Linux RAG stack services",
		SilenceUsage:  true,
		SilenceErrors: true,
		RunE: func(cmd *cobra.Command, args []string) error {
			configPath, err := rootOpts.requireConfig(cmd)
			if err != nil {
				return err
			}

			if _, err := os.Stat(configPath); err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("failed to access config file: %v", err))
			}

			cfg, err := loadConfig(configPath)
			if err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("failed to load config: %v", err))
			}

			if err := ensureDirectories(cfg); err != nil {
				return errorWithGuidance(cmd, err.Error())
			}

			if err := startStackProcess(cmd, cfg); err != nil {
				return err
			}

			if err := launchServer(cmd, configPath); err != nil {
				return err
			}

			if opts.waitReady {
				timeout := time.Duration(cfg.Stack.WaitTimeoutSeconds * float64(time.Second))
				if timeout <= 0 {
					timeout = defaultWaitTimeout
				}
				if err := waitForReady(cmd.Context(), cfg.Runtime.SocketPath, timeout); err != nil {
					return errorWithGuidance(cmd, err.Error())
				}
			}

			return nil
		},
	}

	cmd.Flags().BoolVar(&opts.waitReady, "wait-ready", false, "Block until the stack reports ready status")
	cmd.SetFlagErrorFunc(func(c *cobra.Command, err error) error {
		return newFlagParseError(c, err)
	})
	return cmd
}

func ensureDirectories(cfg adminConfig) error {
	dirs := []string{
		cfg.Paths.DataRoot,
		cfg.Paths.CacheDir,
		cfg.Paths.WeaviateDataDir,
		cfg.Paths.OllamaModelsDir,
		cfg.Paths.KiwixArchivesDir,
		cfg.Paths.LogsDir,
		filepath.Join(cfg.Paths.DataRoot, "state"),
	}
	for _, dir := range dirs {
		if dir == "" {
			continue
		}
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return fmt.Errorf("unable to create directory %s: %w", dir, err)
		}
	}
	return nil
}

func startStackProcess(cmd *cobra.Command, cfg adminConfig) error {
	binary := cfg.Stack.Binary
	args := []string{
		"-f", cfg.Stack.ComposeFile,
		"--project-name", cfg.Stack.ProjectName,
		"up",
		"--detach",
	}
	compose := exec.CommandContext(cmd.Context(), binary, args...)
	compose.Stdout = cmd.OutOrStdout()
	compose.Stderr = cmd.ErrOrStderr()
	env := os.Environ()
	env = append(env,
		fmt.Sprintf("LINUX_RAG_DATA_ROOT=%s", cfg.Paths.DataRoot),
		fmt.Sprintf("LINUX_RAG_PROJECT=%s", cfg.Stack.ProjectName),
		fmt.Sprintf("LINUX_RAG_COMPOSE_FILE=%s", cfg.Stack.ComposeFile),
	)
	for k, v := range cfg.Stack.Environment {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}
	compose.Env = env
	if err := compose.Run(); err != nil {
		return errorWithGuidance(cmd, fmt.Sprintf("failed to start stack: %v", err))
	}
	return nil
}

func launchServer(cmd *cobra.Command, configPath string) error {
	repoRoot := filepath.Dir(filepath.Dir(configPath))
	serverCmd := exec.CommandContext(cmd.Context(), "uv", "run", "python", "-m", "linux_rag.server.main", "--config", configPath)
	if _, err := os.Stat(repoRoot); err == nil {
		serverCmd.Dir = repoRoot
	}
	serverCmd.Stdout = cmd.OutOrStdout()
	serverCmd.Stderr = cmd.ErrOrStderr()
	if err := serverCmd.Start(); err != nil {
		return errorWithGuidance(cmd, fmt.Sprintf("failed to launch server: %v", err))
	}

	go func() {
		if err := serverCmd.Wait(); err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "linux_rag.server.main exited: %v\n", err)
		}
	}()

	return nil
}

func waitForReady(ctx context.Context, socket string, timeout time.Duration) error {
	if timeout <= 0 {
		timeout = defaultWaitTimeout
	}
	deadline := time.Now().Add(timeout)
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		err := checkStatus(ctx, socket)
		if err == nil {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("timed out waiting for stack readiness: %w", err)
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func checkStatus(ctx context.Context, socket string) error {
	conn, err := dialEndpoint(ctx, socket, 3*time.Second)
	if err != nil {
		return err
	}
	defer conn.Close()

	client := contractspb.NewRagServiceClient(conn)
	rpcCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	_, err = client.GetStatus(rpcCtx, &contractspb.GetStatusRequest{})
	return err
}

func newIngestCmd(rootOpts *rootOptions) *cobra.Command {
	opts := ingestOptions{}
	cmd := &cobra.Command{
		Use:           "ingest",
		Short:         "Trigger document ingestion",
		SilenceUsage:  true,
		SilenceErrors: true,
		RunE: func(cmd *cobra.Command, args []string) error {
			opts.wikiArchives = filterEmpty(opts.wikiArchives)
			opts.refreshManual = strings.TrimSpace(opts.manRoot) != ""

			if !opts.refreshManual && len(opts.wikiArchives) == 0 {
				return errorWithGuidance(cmd, "ingest requires --man-root or at least one --wiki archive")
			}

			configPath, err := rootOpts.requireConfig(cmd)
			if err != nil {
				return err
			}

			if _, err := os.Stat(configPath); err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("failed to access config file: %v", err))
			}

			cfg, err := loadConfig(configPath)
			if err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("failed to load config: %v", err))
			}

			if err := runIngestion(cmd.Context(), cfg, opts, cmd); err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("ingestion failed: %v", err))
			}

			return nil
		},
	}

	cmd.Flags().StringVar(&opts.manRoot, "man-root", "", "Path to the man page root to ingest")
	cmd.Flags().StringSliceVar(&opts.wikiArchives, "wiki", nil, "Kiwix archive identifiers to ingest (repeatable)")
	cmd.SetFlagErrorFunc(func(c *cobra.Command, err error) error {
		return newFlagParseError(c, err)
	})

	return cmd
}

func runIngestion(ctx context.Context, cfg adminConfig, opts ingestOptions, cmd *cobra.Command) error {
	conn, err := dialEndpoint(ctx, cfg.Runtime.SocketPath, defaultRPCDeadline)
	if err != nil {
		return err
	}
	defer conn.Close()

	client := contractspb.NewRagServiceClient(conn)
	rpcCtx, cancel := context.WithTimeout(ctx, defaultRPCDeadline)
	defer cancel()

	req := &contractspb.RunIngestionRequest{
		WikiArchiveIds:  opts.wikiArchives,
		RefreshManPages: opts.refreshManual,
	}

	resp, err := client.RunIngestion(rpcCtx, req)
	if err != nil {
		return err
	}

	fmt.Fprintf(cmd.OutOrStdout(), "Started ingestion job %s\n", resp.GetJobId())
	fmt.Fprintf(cmd.OutOrStdout(), "Man pages processed: %d\n", resp.GetManPagesProcessed())
	fmt.Fprintf(cmd.OutOrStdout(), "Wiki articles processed: %d\n", resp.GetWikiArticlesProcessed())
	if len(resp.GetErrors()) > 0 {
		fmt.Fprintln(cmd.ErrOrStderr(), "Errors encountered during ingestion:")
		for _, item := range resp.GetErrors() {
			fmt.Fprintf(cmd.ErrOrStderr(), "- %s: %s\n", item.GetSource(), item.GetErrorMessage())
		}
	}

	return nil
}

func newStatusCmd(rootOpts *rootOptions) *cobra.Command {
	opts := statusOptions{format: string(FormatText)}
	cmd := &cobra.Command{
		Use:           "status",
		Short:         "Fetch status information from the stack",
		SilenceUsage:  true,
		SilenceErrors: true,
		RunE: func(cmd *cobra.Command, args []string) error {
			format := strings.ToLower(strings.TrimSpace(opts.format))
			if !contains(allowedStatusFormats, format) {
				return newFlagValueError(cmd, "format", opts.format, allowedStatusFormats)
			}

			configPath, err := rootOpts.requireConfig(cmd)
			if err != nil {
				return err
			}

			if _, err := os.Stat(configPath); err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("failed to access config file: %v", err))
			}

			cfg, err := loadConfig(configPath)
			if err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("failed to load config: %v", err))
			}

			view, err := fetchStatus(cmd.Context(), cfg)
			if err != nil {
				return errorWithGuidance(cmd, fmt.Sprintf("failed to fetch status: %v", err))
			}

			rendered, err := RenderStatus(view, OutputFormat(format))
			if err != nil {
				return err
			}

			fmt.Fprintln(cmd.OutOrStdout(), rendered)
			return nil
		},
	}

	cmd.Flags().StringVar(&opts.format, "format", opts.format, "Output format (text or json)")
	cmd.SetFlagErrorFunc(func(c *cobra.Command, err error) error {
		return newFlagParseError(c, err)
	})

	return cmd
}

func fetchStatus(ctx context.Context, cfg adminConfig) (StatusView, error) {
	conn, err := dialEndpoint(ctx, cfg.Runtime.SocketPath, defaultRPCDeadline)
	if err != nil {
		return StatusView{}, err
	}
	defer conn.Close()

	client := contractspb.NewRagServiceClient(conn)
	rpcCtx, cancel := context.WithTimeout(ctx, defaultRPCDeadline)
	defer cancel()

	resp, err := client.GetStatus(rpcCtx, &contractspb.GetStatusRequest{})
	if err != nil {
		return StatusView{}, err
	}

	view := StatusView{
		LatestJobID:      resp.GetLatestJobId(),
		LatestJobStatus:  resp.GetLatestJobStatus(),
		CacheDiskPercent: resp.GetCacheDiskPct(),
		CacheHitRate:     int(resp.GetCacheHitRate()),
		ActiveModels:     resp.GetActiveModels(),
		LastSuccessAt:    resp.GetLatestJobCompletedAt(),
		Errors:           nil,
	}
	return view, nil
}

func dialEndpoint(ctx context.Context, socket string, timeout time.Duration) (*grpc.ClientConn, error) {
	target := strings.TrimSpace(socket)
	opts := []grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}
	if strings.HasPrefix(target, "tcp://") {
		target = strings.TrimPrefix(target, "tcp://")
	} else {
		path := strings.TrimPrefix(target, "unix://")
		if path == "" {
			path = target
		}
		target = "unix://" + path
		opts = append(opts, grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return net.DialTimeout("unix", path, timeout)
		}))
	}

	dialCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	conn, err := grpc.DialContext(dialCtx, target, opts...)
	if err != nil {
		return nil, err
	}
	return conn, nil
}

func filterEmpty(input []string) []string {
	if len(input) == 0 {
		return nil
	}
	out := make([]string, 0, len(input))
	for _, value := range input {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func contains(values []string, candidate string) bool {
	for _, v := range values {
		if strings.EqualFold(v, candidate) {
			return true
		}
	}
	return false
}
