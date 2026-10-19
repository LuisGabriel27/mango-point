import ConfirmationModal from './ConfirmationModal'

export default function LogoutConfirmationModal(props) {
  return <ConfirmationModal {...props} title="Log out of MangoPoint?" confirmLabel="Log out" closeLabel="Close logout confirmation" className="logout-confirmation-backdrop">
    <p>You’ll need to sign in again to continue.</p>
  </ConfirmationModal>
}