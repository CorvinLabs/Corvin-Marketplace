/**
 * Workflows Page — Extracted from CorvinOS console
 *
 * Phases 1-7: List, create, edit, run, approve, schedule, chat
 * Uses plugin API client instead of console auth
 */

import { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

// API client (to be extracted from console)
import {
  listWorkflows,
  getWorkflow,
  createWorkflow,
  updateWorkflowYaml,
  startRun,
  listRuns,
  getRun,
} from './api/workflows';

// UI Components (console-compatible)
import { Button, Card, Dialog, Input, Tabs, Textarea, Badge } from '@/components/ui';
import { Loader2, Plus, Play, Download, Trash2 } from 'lucide-react';

export default function WorkflowsPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);

  // Query: List workflows
  const { data: workflows, isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: listWorkflows,
  });

  // Mutation: Create workflow
  const createMutation = useMutation({
    mutationFn: (data: { title: string; description: string }) =>
      createWorkflow(data.title, data.description),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      navigate(`/app/workflows/${data.wid}`);
      setShowCreate(false);
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Workflows</h1>
          <p className="text-sm text-gray-600 mt-1">
            Design and execute multi-step automation
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          New Workflow
        </Button>
      </div>

      {/* Create Dialog */}
      <CreateWorkflowDialog
        open={showCreate}
        onOpenChange={setShowCreate}
        onCreate={(data) => createMutation.mutate(data)}
        isLoading={createMutation.isPending}
      />

      {/* Workflows Grid */}
      {workflows && workflows.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workflows.map((wf) => (
            <WorkflowCard
              key={wf.wid}
              workflow={wf}
              onClick={() => navigate(`/app/workflows/${wf.wid}`)}
            />
          ))}
        </div>
      ) : (
        <Card className="p-12 text-center">
          <p className="text-gray-600">No workflows yet. Create one to get started.</p>
        </Card>
      )}
    </div>
  );
}

// Subcomponents
function WorkflowCard({
  workflow,
  onClick,
}: {
  workflow: any;
  onClick: () => void;
}) {
  return (
    <Card
      className="p-4 cursor-pointer hover:shadow-lg transition-shadow"
      onClick={onClick}
    >
      <div className="space-y-2">
        <h3 className="font-semibold text-lg truncate">{workflow.title}</h3>
        <p className="text-sm text-gray-600 line-clamp-2">{workflow.description}</p>
        <div className="flex items-center justify-between pt-2">
          <Badge>{workflow.node_count} nodes</Badge>
          <Badge variant="outline">{workflow.status}</Badge>
        </div>
      </div>
    </Card>
  );
}

function CreateWorkflowDialog({
  open,
  onOpenChange,
  onCreate,
  isLoading,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (data: { title: string; description: string }) => void;
  isLoading: boolean;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');

  const handleCreate = () => {
    if (title.trim()) {
      onCreate({ title, description });
      setTitle('');
      setDescription('');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <div className="space-y-4 p-6">
        <Input
          placeholder="Workflow title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Textarea
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={isLoading || !title.trim()}>
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create'}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
