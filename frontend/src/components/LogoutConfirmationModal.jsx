import ConfirmationModal from './ConfirmationModal'

export default function LogoutConfirmationModal(props) {
  return <ConfirmationModal {...props} title="Confirm logout" confirmLabel="Log out" danger showIcon={false} closeLabel="Close logout confirmation" className="logout-confirmation-backdrop">
    <p>Are you sure you want to log out of MangoPoint?</p>
  </ConfirmationModal>
}
