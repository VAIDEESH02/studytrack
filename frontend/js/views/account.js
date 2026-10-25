// "Change password" from the account menu.

import { ApiError, api } from "../api.js";
import { openFormDialog, toast } from "../ui.js";

export async function openChangePasswordDialog() {
  const done = await openFormDialog({
    title: "Change your password",
    description: "You'll stay signed in here. Other devices will be signed out.",
    submitLabel: "Update password",
    fields: [
      {
        name: "current_password",
        label: "Current password",
        type: "password",
        required: true,
        autocomplete: "current-password",
      },
      {
        name: "new_password",
        label: "New password",
        type: "password",
        required: true,
        minlength: 12,
        maxlength: 128,
        autocomplete: "new-password",
        hint: "At least 12 characters. A short phrase is easier to remember than a jumble.",
      },
      {
        name: "confirm_password",
        label: "Confirm new password",
        type: "password",
        required: true,
        autocomplete: "new-password",
      },
    ],
    onSubmit: async ({ current_password, new_password, confirm_password }) => {
      if (new_password !== confirm_password) {
        throw new ApiError(0, "The new passwords don't match.", {
          fieldErrors: { confirm_password: "This doesn't match the new password." },
        });
      }
      await api("/auth/change-password", { method: "POST", body: { current_password, new_password } });
      return true;
    },
  });
  if (done) toast("Password updated. Other devices have been signed out.");
}
