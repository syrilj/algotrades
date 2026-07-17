import type { Metadata } from "next";
import { ProfileWorkspace } from "@/components/profile/ProfileWorkspace";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata: Metadata = {
  title: "Operator Profile — Trade Desk",
  description: "Local operator identity, paper-risk defaults, and data-contract preferences.",
};

export default function ProfilePage() {
  return (
    <div className="td-page td-profile-page">
      <PageHeader
        eyebrow="Workspace"
        title="Operator profile"
        description="Set the identity, model default, paper-risk rails, and data contract used around your local research desk."
        meta="Browser-local preferences · no brokerage credentials"
      />
      <ProfileWorkspace />
    </div>
  );
}
