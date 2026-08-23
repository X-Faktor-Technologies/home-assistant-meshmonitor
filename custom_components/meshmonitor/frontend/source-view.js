import { sourceHealthPresentation } from "./overview.js";

export const sourceCardPresentation = sourceHealthPresentation;

const reported = (value) => value !== null && value !== undefined && value !== "";
const titleCase = (value) => String(value).replace(/(^|[_-])([a-z])/g, (_match, separator, letter) =>
  `${separator ? " " : ""}${letter.toUpperCase()}`);

export function reticulumCardPresentation(source) {
  if (String(source?.protocol || "").toLowerCase() !== "reticulum") return null;
  const details = source?.reticulum || {};
  return {
    stats: [
      {label: "destinations", value: reported(details.destination_count) ? details.destination_count : "—"},
      {label: "interfaces", value: reported(details.interface_count) ? details.interface_count : "—"},
    ],
    primary: [
      ["Connection", sourceCardPresentation(source).connection],
      ["RNS", reported(details.rns_version) ? details.rns_version : "Unknown"],
      ["Bridge", reported(details.bridge_version) ? details.bridge_version : "Unknown"],
    ],
    secondary: [
      ["Mode", reported(details.mode) ? titleCase(details.mode) : "Unknown"],
      ["LXMF identity", reported(details.identity_name) ? details.identity_name : "Unknown"],
      ["Destination", reported(details.identity_hash) ? details.identity_hash : "Unknown"],
    ],
  };
}
