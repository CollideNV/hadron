import type { RichToolCallProps } from "./helpers";
import ReadFileRenderer from "./ReadFileRenderer";
import WriteFileRenderer from "./WriteFileRenderer";
import ListDirectoryRenderer from "./ListDirectoryRenderer";
import RunCommandRenderer from "./RunCommandRenderer";
import SearchFilesRenderer from "./SearchFilesRenderer";
import FallbackRenderer from "./FallbackRenderer";

const TOOL_RENDERERS: Record<string, React.FC<RichToolCallProps>> = {
  read_file: ReadFileRenderer,
  write_file: WriteFileRenderer,
  list_directory: ListDirectoryRenderer,
  run_command: RunCommandRenderer,
  execute_command: RunCommandRenderer,
  bash: RunCommandRenderer,
  search_files: SearchFilesRenderer,
  grep: SearchFilesRenderer,
};

export default function RichToolCall({ call, result }: RichToolCallProps) {
  const Renderer = TOOL_RENDERERS[call.tool] || FallbackRenderer;
  return <Renderer call={call} result={result} />;
}
